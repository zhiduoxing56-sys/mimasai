// BFV coefficient aggregation. Evaluation mode never loads any SecretKey.
#include <seal/seal.h>
#include <seal/util/ntt.h>
#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sys/resource.h>
using namespace seal;
namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;
void check(bool b,const char* s){if(!b)throw std::runtime_error(s);}
double seconds(Clock::time_point a){return std::chrono::duration<double>(Clock::now()-a).count();}
template<class T> void save(const T& x,const fs::path& p){std::ofstream f(p,std::ios::binary);check(bool(f),"HE_FILE_WRITE");x.save(f,compr_mode_type::none);check(bool(f),"HE_FILE_WRITE");fs::permissions(p,fs::perms::owner_read|fs::perms::owner_write);}
template<class T> T load(const SEALContext& c,const fs::path& p){T x;std::ifstream f(p,std::ios::binary);check(bool(f),"HE_FILE_READ");x.load(c,f);check(f.peek()==EOF,"HE_FILE_TRAILING");return x;}
std::vector<std::uint32_t> read32(const fs::path& p,std::size_t count){std::vector<std::uint32_t> a(count);std::ifstream f(p,std::ios::binary);check(bool(f),"HE_FILE_READ");f.read(reinterpret_cast<char*>(a.data()),count*4);check(std::size_t(f.gcount())==count*4&&f.peek()==EOF,"HE_INPUT_LENGTH");return a;}
void write32(const fs::path& p,const std::vector<std::uint32_t>& a){std::ofstream f(p,std::ios::binary);f.write(reinterpret_cast<const char*>(a.data()),a.size()*4);check(bool(f),"HE_FILE_WRITE");fs::permissions(p,fs::perms::owner_read|fs::perms::owner_write);}
EncryptionParameters parameters(const fs::path& d){EncryptionParameters p;std::ifstream f(d/"parameters.seal",std::ios::binary);check(bool(f),"HE_PARAMETERS_READ");p.load(f);check(f.peek()==EOF,"HE_PARAMETERS_TRAILING");return p;}
long peak(){rusage r;getrusage(RUSAGE_SELF,&r);return r.ru_maxrss;}
// ExtractConst: sample (c0[0], c1[0], -c1[N-1],..., -c1[1]).
// Reverse embed is exactly (c0[0],c1); q-limb division by N followed by trace.
Ciphertext project(const Ciphertext& in,const SEALContext& ctx,Evaluator& ev,const GaloisKeys& gk,const std::vector<std::uint32_t>& els){
 check(in.size()==2&&!in.is_ntt_form(),"HE_EXTRACTION_SHAPE");auto data=ctx.get_context_data(in.parms_id());check(bool(data),"HE_PARAMETER_ID");
 const auto& qs=data->parms().coeff_modulus();auto degree=data->parms().poly_modulus_degree();Ciphertext out=in;
 for(std::size_t l=0;l<qs.size();l++){
  auto q=qs[l].value();std::uint64_t inverse;check(util::try_invert_uint_mod(degree,qs[l],inverse),"HE_TRACE_INVERSE");
  auto mul=[&](std::uint64_t v){return std::uint64_t(__uint128_t(v)*inverse%q);};
  auto* c0=out.data(0)+l*degree;c0[0]=mul(c0[0]);std::fill(c0+1,c0+degree,0);
  auto* c1=out.data(1)+l*degree;for(std::size_t j=0;j<degree;j++)c1[j]=mul(c1[j]);
 }
 for(auto el:els){Ciphertext rotated;ev.apply_galois(out,el,gk,rotated);ev.add_inplace(out,rotated);}return out;
}
int main(int argc,char** argv){
 auto begin=Clock::now();
 try{
  check(argc>=3,"HE_USAGE");std::string mode=argv[1];fs::path dir=argv[2];
  if(mode=="setup"){
   check(argc==11,"HE_SETUP_USAGE");auto degree=std::stoul(argv[3]);auto bits=std::stoul(argv[4]);auto nodes=std::stoul(argv[9]);auto cols=std::stoul(argv[10]);
   check(bits==32&&nodes<=degree&&cols>0,"HE_SETUP_SHAPE");EncryptionParameters p(scheme_type::bfv);p.set_poly_modulus_degree(degree);p.set_coeff_modulus(CoeffModulus::Create(degree,{std::stoi(argv[5]),std::stoi(argv[6]),std::stoi(argv[7]),std::stoi(argv[8])}));p.set_plain_modulus(std::uint64_t(1)<<bits);SEALContext ctx(p,true,sec_level_type::tc128);check(ctx.parameters_set(),ctx.parameter_error_message());auto matrix=read32(dir/"V/propagation.bin",nodes*nodes);std::vector<std::uint32_t> els;for(auto d=degree;d>=2;d/=2)els.push_back(d+1);
   std::uint64_t pkbytes=0,skbytes=0,gkbytes=0,rowbytes=0;
   for(int key=0;key<2;key++){
    fs::path own=dir/("S"+std::to_string(key)),peer=dir/("S"+std::to_string(1-key));fs::create_directories(own/"rows");save(p,own/"parameters.seal");KeyGenerator gen(ctx);PublicKey pk;GaloisKeys gk;gen.create_public_key(pk);gen.create_galois_keys(els,gk);save(pk,own/"eval.pk");save(gk,own/"eval.gk");save(gen.secret_key(),peer/"peer.sk");save(gen.secret_key(),dir/("V/key"+std::to_string(key)+".sk"));pkbytes+=fs::file_size(own/"eval.pk");skbytes+=fs::file_size(peer/"peer.sk");gkbytes+=fs::file_size(own/"eval.gk");Encryptor enc(ctx,pk);
    for(std::size_t i=0;i<nodes;i++){Plaintext w(degree);for(std::size_t j=0;j<nodes;j++){auto v=std::uint64_t(matrix[i*nodes+j]);w[j?degree-j:0]=j?((std::uint64_t(1)<<bits)-v)% (std::uint64_t(1)<<bits):v;}Ciphertext ct;enc.encrypt(w,ct);auto path=own/"rows"/(std::to_string(i)+".ct");save(ct,path);rowbytes+=fs::file_size(path);}
   }
   std::cout<<"{\"status\":\"KEYS_AND_NEIGHBORHOODS_READY\",\"security_bits\":128,\"degree\":"<<degree<<",\"galois_elements\":"<<els.size()<<",\"public_key_bytes\":"<<pkbytes<<",\"secret_key_bytes\":"<<skbytes<<",\"evaluation_key_bytes\":"<<gkbytes<<",\"neighborhood_bytes\":"<<rowbytes<<",\"elapsed_seconds\":"<<seconds(begin)<<",\"peak_rss_kib\":"<<peak()<<"}\n";return 0;
  }
  auto p=parameters(dir);SEALContext ctx(p,true,sec_level_type::tc128);check(ctx.parameters_set(),ctx.parameter_error_message());auto degree=p.poly_modulus_degree();check(p.plain_modulus().value()==(std::uint64_t(1)<<32),"HE_RING_MISMATCH");
  if(mode=="eval"){
   check(argc==5,"HE_EVAL_USAGE");auto nodes=std::stoul(argv[3]),cols=std::stoul(argv[4]);check(nodes<=degree&&cols>0,"HE_INPUT_SHAPE");auto pk=load<PublicKey>(ctx,dir/"eval.pk");auto gk=load<GaloisKeys>(ctx,dir/"eval.gk");auto x=read32(dir/"features.bin",nodes*cols);auto masks=read32(dir/"masks.bin",degree*cols);Evaluator ev(ctx);Encryptor zero_encryptor(ctx,pk);std::vector<std::uint32_t> els;for(auto d=degree;d>=2;d/=2)els.push_back(d+1);fs::create_directories(dir/"trace");fs::create_directories(dir/"send");double multiply=0,extract=0,pack=0,mask=0;std::uint64_t ctbytes=0;
   std::vector<Ciphertext> rows;for(std::size_t i=0;i<nodes;i++)rows.push_back(load<Ciphertext>(ctx,dir/"rows"/(std::to_string(i)+".ct")));
   for(std::size_t col=0;col<cols;col++){
    Plaintext f(nodes);for(std::size_t j=0;j<nodes;j++)f[j]=x[j*cols+col];Ciphertext packed;
    for(std::size_t row=0;row<nodes;row++){
     auto a=Clock::now();Ciphertext product;if(f.is_zero())zero_encryptor.encrypt_zero(product);else ev.multiply_plain(rows[row],f,product);multiply+=seconds(a);save(product,dir/"trace"/(std::to_string(col)+"_"+std::to_string(row)+"_multiply.ct"));
     a=Clock::now();auto scalar=project(product,ctx,ev,gk,els);extract+=seconds(a);save(scalar,dir/"trace"/(std::to_string(col)+"_"+std::to_string(row)+"_extract.ct"));
     a=Clock::now();if(row){Plaintext monomial(row+1);monomial[row]=1;Ciphertext shifted;ev.multiply_plain(scalar,monomial,shifted);ev.add_inplace(packed,shifted);}else packed=std::move(scalar);pack+=seconds(a);
    }
    save(packed,dir/"trace"/(std::to_string(col)+"_packed.ct"));auto a=Clock::now();Plaintext maskpt(degree);for(std::size_t j=0;j<degree;j++)maskpt[j]=masks[col*degree+j];ev.sub_plain_inplace(packed,maskpt);mask+=seconds(a);auto target=dir/"send"/(std::to_string(col)+".ct");save(packed,target);ctbytes+=fs::file_size(target);
   }
   std::cout<<"{\"status\":\"EVALUATED_WITHOUT_SECRET_KEY\",\"multiply_seconds\":"<<multiply<<",\"extract_trace_seconds\":"<<extract<<",\"pack_seconds\":"<<pack<<",\"full_mask_seconds\":"<<mask<<",\"ciphertext_bytes\":"<<ctbytes<<",\"elapsed_seconds\":"<<seconds(begin)<<",\"peak_rss_kib\":"<<peak()<<"}\n";return 0;
  }
  if(mode=="decrypt"){
   check(argc==4,"HE_DECRYPT_USAGE");auto cols=std::stoul(argv[3]);auto sk=load<SecretKey>(ctx,dir/"peer.sk");Decryptor dec(ctx,sk);std::vector<std::uint32_t> all;all.reserve(cols*degree);
   for(std::size_t c=0;c<cols;c++){auto ct=load<Ciphertext>(ctx,dir/"receive"/(std::to_string(c)+".ct"));Plaintext out;dec.decrypt(ct,out);for(std::size_t j=0;j<degree;j++)all.push_back(j<out.coeff_count()?out[j]:0);}write32(dir/"decrypted.bin",all);std::cout<<"{\"status\":\"CROSS_KEY_MASKED_DECRYPTION\",\"elapsed_seconds\":"<<seconds(begin)<<",\"peak_rss_kib\":"<<peak()<<"}\n";return 0;
  }
  if(mode=="mask_audit"){
   check(argc==5,"HE_MASK_AUDIT_USAGE");auto a=load<Ciphertext>(ctx,argv[3]);auto b=load<Ciphertext>(ctx,argv[4]);check(a.parms_id()==b.parms_id()&&a.size()==b.size(),"HE_MASK_AUDIT_SHAPE");auto size=degree*ctx.get_context_data(a.parms_id())->parms().coeff_modulus().size();bool equal=std::equal(a.data(1),a.data(1)+size,b.data(1));std::cout<<"{\"ciphertext_component_one_unchanged\":"<<(equal?"true":"false")<<"}\n";return 0;
  }
  if(mode=="oracle"){
   check(argc==6,"HE_ORACLE_USAGE");auto sk=load<SecretKey>(ctx,argv[3]);Decryptor dec(ctx,sk);auto ct=load<Ciphertext>(ctx,argv[4]);Plaintext out;dec.decrypt(ct,out);std::vector<std::uint32_t> all(degree);for(std::size_t j=0;j<out.coeff_count();j++)all[j]=out[j];write32(argv[5],all);std::cout<<"{\"noise_bits\":"<<dec.invariant_noise_budget(ct)<<"}\n";return 0;
  }
  throw std::runtime_error("HE_UNKNOWN_MODE");
 }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 2;}
}
