#include <GlobalParams.h>
#include <PDFDoc.h>
#include <TextOutputDev.h>
#include <goo/GooString.h>
#include <memory>
int main(int argc,char **argv) {
    if(argc!=4) return 2;
    globalParams=std::make_unique<GlobalParams>(argv[1]);
    PDFDoc doc(std::make_unique<GooString>(argv[2]));
    if(!doc.isOk()) return 1;
    TextOutputDev out(argv[3],true,0,false,false);
    if(!out.isOk()) return 1;
    doc.displayPages(&out,1,doc.getNumPages(),72,72,0,false,true,false);
}
