// BFV coefficient aggregation. Evaluation mode never loads any SecretKey.
#include <seal/seal.h>
#include <seal/util/ntt.h>
#include <seal/util/rlwe.h>
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
using Poly=std::vector<std::uint64_t>;
Poly read64(const fs::path& path,std::size_t count){Poly v(count);std::ifstream f(path,std::ios::binary);check(bool(f),"RING_FILE_READ");f.read(reinterpret_cast<char*>(v.data()),count*8);check(std::size_t(f.gcount())==count*8&&f.peek()==EOF,"RING_FILE_LENGTH");return v;}
void write64(const fs::path& path,const Poly& v){check(!fs::exists(path),"RING_IMMUTABLE_FILE");std::ofstream f(path,std::ios::binary);f.write(reinterpret_cast<const char*>(v.data()),v.size()*8);check(bool(f),"RING_FILE_WRITE");fs::permissions(path,fs::perms::owner_read|fs::perms::owner_write);}
void canonical(const Poly& a,const SEALContext& ctx){auto d=ctx.first_context_data();auto n=d->parms().poly_modulus_degree();const auto& qs=d->parms().coeff_modulus();check(a.size()==n*qs.size(),"RING_SHAPE");for(std::size_t l=0;l<qs.size();l++)for(std::size_t j=0;j<n;j++)check(a[l*n+j]<qs[l].value(),"RING_RESIDUE");}
Poly ringmul(Poly a,Poly b,const SEALContext& ctx){canonical(a,ctx);canonical(b,ctx);auto d=ctx.first_context_data();auto n=d->parms().poly_modulus_degree();const auto& qs=d->parms().coeff_modulus();for(std::size_t l=0;l<qs.size();l++){util::ntt_negacyclic_harvey(a.data()+l*n,d->small_ntt_tables()[l]);util::ntt_negacyclic_harvey(b.data()+l*n,d->small_ntt_tables()[l]);for(std::size_t j=0;j<n;j++)a[l*n+j]=std::uint64_t(__uint128_t(a[l*n+j])*b[l*n+j]%qs[l].value());util::inverse_ntt_negacyclic_harvey(a.data()+l*n,d->small_ntt_tables()[l]);}return a;}
Poly randompoly(const SEALContext& ctx){const auto& p=ctx.first_context_data()->parms();Poly a(p.poly_modulus_degree()*p.coeff_modulus().size());auto rng=p.random_generator()->create();util::sample_poly_uniform(rng,p,a.data());return a;}
void moduli_json(const SEALContext& ctx){std::cout<<"[";bool first=true;for(const auto& q:ctx.first_context_data()->parms().coeff_modulus()){if(!first)std::cout<<",";std::cout<<q.value();first=false;}std::cout<<"]";}
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
  if(mode=="metadata"){check(argc==3,"RING_METADATA_USAGE");std::cout<<"{\"degree\":"<<degree<<",\"security_bits\":128,\"data_moduli\":";moduli_json(ctx);std::cout<<"}\n";return 0;}
  if(mode=="ring_preprocess"){
   check(argc==4,"RING_PREPROCESS_USAGE");auto count=std::stoul(argv[3]);auto data=ctx.first_context_data();auto n=data->parms().poly_modulus_degree();const auto& qs=data->parms().coeff_modulus();
   for(std::size_t i=0;i<count;i++){auto a=randompoly(ctx),b=randompoly(ctx),c=ringmul(a,b,ctx);std::vector<Poly> full={a,b,c};for(std::size_t k=0;k<3;k++){auto share=randompoly(ctx);Poly peer(share.size());for(std::size_t l=0;l<qs.size();l++)for(std::size_t j=0;j<n;j++){auto idx=l*n+j;peer[idx]=(full[k][idx]+qs[l].value()-share[idx])%qs[l].value();}for(int role=0;role<2;role++){auto folder=dir/("S"+std::to_string(role))/"ring-preprocessing"/std::to_string(i);fs::create_directories(folder);fs::permissions(folder,fs::perms::owner_all);write64(folder/(std::string(1,"abc"[k])+".bin"),role==0?share:peer);}}}
   std::cout<<"{\"status\":\"INPUT_INDEPENDENT_RING_TRIPLES\",\"items\":"<<count<<",\"degree\":"<<degree<<",\"security_bits\":128,\"data_moduli\":";moduli_json(ctx);std::cout<<",\"elapsed_seconds\":"<<seconds(begin)<<"}\n";return 0;
  }
  if(mode=="ring_evaluate"){
   check(argc==7,"RING_EVALUATE_USAGE");int role=std::stoi(argv[3]);check(role==0||role==1,"RING_ROLE");auto n=degree;const auto& qs=ctx.first_context_data()->parms().coeff_modulus();auto count=n*qs.size();auto d=read64(dir/"ring-work/d.bin",count),e=read64(dir/"ring-work/e.bin",count);fs::path triple=argv[4];auto a=read64(triple/"a.bin",count),b=read64(triple/"b.bin",count),c=read64(triple/"c.bin",count);canonical(c,ctx);auto db=ringmul(d,b,ctx),ea=ringmul(e,a,ctx);Poly de(count);if(role==0)de=ringmul(d,e,ctx);for(std::size_t l=0;l<qs.size();l++)for(std::size_t j=0;j<n;j++){auto i=l*n+j;c[i]=(c[i]+db[i]+ea[i]+de[i])%qs[l].value();}write64(argv[5],c);check(std::string(argv[6])=="no_decryption","RING_MODE");std::cout<<"{\"status\":\"SHARED_RING_PRODUCT\",\"elapsed_seconds\":"<<seconds(begin)<<"}\n";return 0;
  }
  if(mode=="export_ring_inputs"){
   check(argc==4,"RING_EXPORT_USAGE");auto cols=std::stoul(argv[3]);auto size=degree*ctx.first_context_data()->parms().coeff_modulus().size();auto sk=load<SecretKey>(ctx,dir/"peer.sk");Poly secret(sk.data().data(),sk.data().data()+size);for(std::size_t l=0;l<size/degree;l++)util::inverse_ntt_negacyclic_harvey(secret.data()+l*degree,ctx.key_context_data()->small_ntt_tables()[l]);canonical(secret,ctx);write64(dir/"peer-key-coefficients.bin",secret);
   for(std::size_t col=0;col<cols;col++){auto ct=load<Ciphertext>(ctx,dir/"send"/(std::to_string(col)+".ct"));check(ct.size()==2&&!ct.is_ntt_form()&&ct.parms_id()==ctx.first_parms_id(),"RING_EXPORT_LEVEL");for(std::size_t k=0;k<2;k++)write64(dir/("cipher-"+std::to_string(col)+"-"+std::to_string(k)+".bin"),Poly(ct.data(k),ct.data(k)+size));}
   std::cout<<"{\"status\":\"LOCAL_COMPONENTS_ONLY_NO_DECRYPTION\",\"data_moduli\":";moduli_json(ctx);std::cout<<"}\n";return 0;
  }
  if(mode=="eval"){
   check(argc==5||argc==6,"HE_EVAL_USAGE");bool trace=argc==5||std::string(argv[5])=="trace";check(argc==5||trace||std::string(argv[5])=="no_trace","HE_TRACE_MODE");auto nodes=std::stoul(argv[3]),cols=std::stoul(argv[4]);check(nodes<=degree&&cols>0,"HE_INPUT_SHAPE");auto pk=load<PublicKey>(ctx,dir/"eval.pk");auto gk=load<GaloisKeys>(ctx,dir/"eval.gk");auto x=read32(dir/"features.bin",nodes*cols);auto masks=read32(dir/"masks.bin",degree*cols);Evaluator ev(ctx);Encryptor zero_encryptor(ctx,pk);std::vector<std::uint32_t> els;for(auto d=degree;d>=2;d/=2)els.push_back(d+1);if(trace)fs::create_directories(dir/"trace");fs::create_directories(dir/"send");double multiply=0,extract=0,pack=0,mask=0;std::uint64_t ctbytes=0;
   std::vector<Ciphertext> rows;for(std::size_t i=0;i<nodes;i++)rows.push_back(load<Ciphertext>(ctx,dir/"rows"/(std::to_string(i)+".ct")));
   for(std::size_t col=0;col<cols;col++){
    Plaintext f(nodes);for(std::size_t j=0;j<nodes;j++)f[j]=x[j*cols+col];Ciphertext packed;
    for(std::size_t row=0;row<nodes;row++){
     auto a=Clock::now();Ciphertext product;if(f.is_zero())zero_encryptor.encrypt_zero(product);else ev.multiply_plain(rows[row],f,product);multiply+=seconds(a);if(trace)save(product,dir/"trace"/(std::to_string(col)+"_"+std::to_string(row)+"_multiply.ct"));
     a=Clock::now();auto scalar=project(product,ctx,ev,gk,els);extract+=seconds(a);if(trace)save(scalar,dir/"trace"/(std::to_string(col)+"_"+std::to_string(row)+"_extract.ct"));
     a=Clock::now();if(row){Plaintext monomial(row+1);monomial[row]=1;Ciphertext shifted;ev.multiply_plain(scalar,monomial,shifted);ev.add_inplace(packed,shifted);}else packed=std::move(scalar);pack+=seconds(a);
    }
    if(trace)save(packed,dir/"trace"/(std::to_string(col)+"_packed.ct"));auto a=Clock::now();Plaintext maskpt(degree);for(std::size_t j=0;j<degree;j++)maskpt[j]=masks[col*degree+j];ev.sub_plain_inplace(packed,maskpt);mask+=seconds(a);auto target=dir/"send"/(std::to_string(col)+".ct");save(packed,target);ctbytes+=fs::file_size(target);
   }
   std::cout<<"{\"status\":\"EVALUATED_WITHOUT_SECRET_KEY\",\"trace_saved\":"<<(trace?"true":"false")<<",\"multiply_seconds\":"<<multiply<<",\"extract_trace_seconds\":"<<extract<<",\"pack_seconds\":"<<pack<<",\"full_mask_seconds\":"<<mask<<",\"ciphertext_bytes\":"<<ctbytes<<",\"elapsed_seconds\":"<<seconds(begin)<<",\"peak_rss_kib\":"<<peak()<<"}\n";return 0;
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
