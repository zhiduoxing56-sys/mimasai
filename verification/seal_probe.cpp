#include <seal/seal.h>
#include <iostream>
#include <stdexcept>
#include <cstdint>
#include <cmath>
#include <seal/util/ntt.h>
#include <vector>
using namespace seal;
void require(bool ok, const char *msg) { if (!ok) throw std::runtime_error(msg); }
int main(int argc, char **argv) {
    try {
        require(argc == 12, "usage: seal_probe degree ring_bits fraction_bits qbit0 qbit1 qbit2 qbit3 weight0 weight1 feature0 feature1");
        const auto n = std::stoul(argv[1]);
        const auto bits = std::stoul(argv[2]);
        const std::uint64_t t = std::uint64_t(1) << bits;
        EncryptionParameters p(scheme_type::bfv);
        p.set_poly_modulus_degree(n);
        p.set_coeff_modulus(CoeffModulus::Create(n, {std::stoi(argv[4]),std::stoi(argv[5]),std::stoi(argv[6]),std::stoi(argv[7])}));
        p.set_plain_modulus(t);
        SEALContext ctx(p, true, sec_level_type::tc128);
        require(ctx.parameters_set(), ctx.parameter_error_message());
        std::cout << "{\"stage\":\"parameters\",\"degree\":" << n
                  << ",\"security\":128,\"valid\":true,\"coeff_modulus_bits\":[";
        bool pf=true;
        for(auto &q:p.coeff_modulus()) { if(!pf) std::cout<<","; pf=false; std::cout<<q.bit_count(); }
        std::cout << "]}\n";
        KeyGenerator kg(ctx);
        PublicKey pk; kg.create_public_key(pk);
        RelinKeys rk; kg.create_relin_keys(rk);
        Encryptor enc(ctx, pk);
        Evaluator ev(ctx);
        Decryptor dec(ctx, kg.secret_key()); // Test oracle only.
        Plaintext weights(n), features(n), answer;
        const std::int64_t scale = std::int64_t(1)<<std::stoul(argv[3]);
        const std::int64_t a=std::stoll(argv[8]), b=std::stoll(argv[9]);
        const std::int64_t x=std::stoll(argv[10]), y=std::stoll(argv[11]);
        weights[0]=a; weights[n-1]=(t-b)%t;
        features[0]=(t+x)%t; features[1]=y;
        const std::uint64_t expected = (t+a*x+b*y)%t;
        Ciphertext cw, cx, cp, cc;
        enc.encrypt(weights, cw); enc.encrypt(features, cx);
        dec.decrypt(cw, answer);
        require(answer == weights, "roundtrip weights mismatch");
        dec.decrypt(cx, answer);
        require(answer[0]==features[0] && answer[1]==features[1], "roundtrip features mismatch");
        ev.multiply_plain(cw, features, cp);
        dec.decrypt(cp, answer);
        require(answer[0]==expected, "ciphertext plaintext constant mismatch");
        auto np = dec.invariant_noise_budget(cp);
        require(np>0, "no ct-pt noise budget");
        std::cout << "{\"stage\":\"roundtrip_and_ct_pt\",\"degree\":" << n
                  << ",\"passed\":true,\"noise\":" << np << "}\n";
        Plaintext share0(n),share1(n);
        share0[0]=t-1234567; share0[1]=t/2+9; // Full-ring algebra test shares.
        share1[0]=(features[0]+t-share0[0])%t;
        share1[1]=(features[1]+t-share0[1])%t;
        Ciphertext local0,local1,shared_sum;
        ev.multiply_plain(cw,share0,local0); ev.multiply_plain(cw,share1,local1);
        ev.add(local0,local1,shared_sum);
        dec.decrypt(shared_sum,answer);
        auto shared_noise=dec.invariant_noise_budget(shared_sum);
        require(answer[0]==expected && shared_noise>0,"local feature-share multiplication failed");
        std::cout<<"{\"stage\":\"local_plaintext_shares\",\"passed\":true,\"noise\":"<<shared_noise<<"}\n";
        ev.multiply(cw, cx, cc);
        const auto before = cc.size();
        dec.decrypt(cc, answer);
        std::cout << "{\"stage\":\"ct_ct_before_relinearization\",\"degree\":" << n
                  << ",\"noise\":" << dec.invariant_noise_budget(cc)
                  << ",\"constant_correct\":" << (answer[0]==expected?"true":"false") << "}\n";
        require(answer[0]==expected, "ciphertext ciphertext constant mismatch");
        auto nm = dec.invariant_noise_budget(cc);
        ev.relinearize_inplace(cc, rk);
        dec.decrypt(cc, answer);
        require(answer[0]==expected && cc.size()==2, "relinearization mismatch");
        auto nr = dec.invariant_noise_budget(cc);
        require(nm>0 && nr>0, "no ct-ct noise budget");
        // Protocol operation: sample-extract coefficient zero without a secret key.
        // BFV ciphertext relation is c0+c1*s. Each RNS limb defines an LWE sample.
        require(!cc.is_ntt_form(), "sample extraction requires coefficient representation");
        std::vector<std::vector<std::uint64_t>> sample_a;
        std::vector<std::uint64_t> sample_b;
        const auto &moduli=ctx.get_context_data(cc.parms_id())->parms().coeff_modulus();
        for(std::size_t l=0;l<moduli.size();++l) {
            auto q=moduli[l].value();
            std::vector<std::uint64_t> a(n);
            auto c1=cc.data(1)+l*n;
            a[0]=c1[0];
            for(std::size_t j=1;j<n;++j) a[j]=c1[n-j]?q-c1[n-j]:0;
            sample_a.push_back(std::move(a)); sample_b.push_back(cc.data(0)[l*n]);
        }
        // Test oracle only: evaluate extracted sample under the coefficient secret.
        const auto &secret=kg.secret_key().data();
        std::vector<std::uint64_t> secret_coeff(secret.data(),secret.data()+secret.coeff_count());
        auto tables=ctx.key_context_data()->small_ntt_tables();
        for(std::size_t l=0;l<p.coeff_modulus().size();++l)
            util::inverse_ntt_negacyclic_harvey(secret_coeff.data()+l*n,tables[l]);
        std::cout << "{\"stage\":\"sample_extraction\",\"moduli\":[";
        for(std::size_t l=0;l<moduli.size();++l) { if(l)std::cout<<","; std::cout<<moduli[l].value(); }
        std::cout << "],\"phase_residues\":[";
        for(std::size_t l=0;l<moduli.size();++l) {
            auto q=moduli[l].value(), phase=sample_b[l];
            for(std::size_t j=0;j<n;++j)
                phase=(phase+static_cast<std::uint64_t>((static_cast<__uint128_t>(sample_a[l][j])*secret_coeff[l*n+j])%q))%q;
            if(l)std::cout<<","; std::cout<<phase;
        }
        std::cout << "],\"expected_plaintext\":" << expected << ",\"plain_modulus\":" << t << "}\n";
        // Independent experimental scalar repacking via ciphertext-modulus normalization
        // and Galois trace. Normalize in each q limb, NOT by an inverse of N mod t.
        std::vector<std::uint32_t> elements;
        for(std::size_t divisor=n;divisor>=2;divisor/=2) elements.push_back(divisor+1);
        GaloisKeys gk; kg.create_galois_keys(elements,gk);
        auto pack_scalar=[&](const std::vector<std::vector<std::uint64_t>> &a_parts,
                            const std::vector<std::uint64_t> &b_parts) {
        Ciphertext scalar=cc;
        std::fill(scalar.data(),scalar.data()+scalar.size()*n*moduli.size(),0);
        for(std::size_t l=0;l<moduli.size();++l) {
            auto q=moduli[l].value();
            std::uint64_t inverse;
            require(util::try_invert_uint_mod(n,moduli[l],inverse), "N not invertible in coefficient modulus");
            auto mul=[&](std::uint64_t a) { return static_cast<std::uint64_t>((static_cast<__uint128_t>(a)*inverse)%q); };
            scalar.data(0)[l*n]=mul(b_parts[l]);
            scalar.data(1)[l*n]=mul(a_parts[l][0]);
            for(std::size_t j=1;j<n;++j)
                scalar.data(1)[l*n+j]=mul(a_parts[l][n-j]?q-a_parts[l][n-j]:0);
        }
        for(auto element:elements) {
            Ciphertext rotated;
            ev.apply_galois(scalar,element,gk,rotated);
            ev.add_inplace(scalar,rotated);
        }
        return scalar;
        };
        Ciphertext scalar=pack_scalar(sample_a,sample_b);
        std::vector<std::vector<std::uint64_t>> second_a;
        std::vector<std::uint64_t> second_b;
        require(cw.parms_id()==cc.parms_id(),"second scalar parameter mismatch");
        for(std::size_t l=0;l<moduli.size();++l) {
            auto q=moduli[l].value();
            std::vector<std::uint64_t> a2(n);
            auto c1=cw.data(1)+l*n;
            a2[0]=c1[0];
            for(std::size_t j=1;j<n;++j) a2[j]=c1[n-j]?q-c1[n-j]:0;
            second_a.push_back(std::move(a2)); second_b.push_back(cw.data(0)[l*n]);
        }
        Ciphertext second_scalar=pack_scalar(second_a,second_b);
        Ciphertext shifted,packed;
        Plaintext monomial(2); monomial[1]=1;
        ev.multiply_plain(second_scalar,monomial,shifted);
        ev.add(scalar,shifted,packed);
        // Only now decrypt for tests; no decryption/re-encryption in repacking.
        dec.decrypt(scalar,answer);
        const auto scalar_noise=dec.invariant_noise_budget(scalar);
        bool scalar_ok=answer[0]==expected;
        for(std::size_t j=1;j<answer.coeff_count();++j) scalar_ok=scalar_ok&&answer[j]==0;
        dec.decrypt(packed,answer);
        const auto packed_noise=dec.invariant_noise_budget(packed);
        bool packed_ok=answer[0]==expected && answer[1]==static_cast<std::uint64_t>(a);
        for(std::size_t j=2;j<answer.coeff_count();++j) packed_ok=packed_ok&&answer[j]==0;
        std::cout<<"{\"stage\":\"experimental_trace_repack\",\"scalar_correct\":"<<(scalar_ok?"true":"false")
                 <<",\"packed_correct\":"<<(packed_ok?"true":"false")<<",\"scalar_noise\":"<<scalar_noise
                 <<",\"packed_noise\":"<<packed_noise<<",\"galois_key_count\":"<<elements.size()<<"}\n";
        require(scalar_ok && packed_ok && scalar_noise>0 && packed_noise>0,"experimental trace repacking failed");
        std::cout << "{\"degree\":" << n << ",\"plain_modulus\":" << t
                  << ",\"security\":128,\"coeff_modulus_bits\":[";
        bool first=true;
        for (auto &q:p.coeff_modulus()) { if(!first) std::cout<<","; first=false; std::cout<<q.bit_count(); }
        std::cout << "],\"batching\":" << (ctx.first_context_data()->qualifiers().using_batching?"true":"false")
                  << ",\"constant\":" << expected << ",\"cipher_size_before\":" << before
                  << ",\"cipher_size_after\":" << cc.size()
                  << ",\"noise_ct_pt\":" << np << ",\"noise_ct_ct\":" << nm
                  << ",\"noise_relinearized\":" << nr
                  << ",\"status\":\"PASS_MINIMAL_HE_AND_EXPERIMENTAL_REPACK\",\"extract_repack\":\"PASS_TWO_COEFFICIENT_SAMPLE\"}\n";
        return 0;
    } catch(const std::exception &e) { std::cerr << e.what() << "\n"; return 1; }
}
