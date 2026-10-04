"""Public source/metadata view audit and targeted role-private-path rejection."""
import ast,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.mpc import ROOT,ProtocolError,costs
from src.application import paths,read

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--experiment',required=True);a=p.parse_args();root,out=paths(a.experiment)
    tree=ast.parse((ROOT/'src/application.py').read_text());reads=[ast.unparse(n) for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='read'];assert not any('input-shares' in s or 'output-' in s or 'model-' in s for s in reads)
    failures=[]
    for role in (0,1):
        fake_source=root/f'S{1-role}'
        request=next(q for q in out.glob('request-*.json') if (Path(read(q)['directory'])/'job-template.json').is_file());d=Path(read(request)['directory'])
        proc=subprocess.run([sys.executable,'-m','src.role_io','query_input',str(role),str(fake_source),str(d)],cwd=ROOT,capture_output=True,text=True)
        assert proc.returncode!=0 and 'ROLE_IO_PRIVATE_VIEW' in proc.stderr
        failures.append(dict(role=role,error='ROLE_IO_PRIVATE_VIEW'))
    invalid=[]
    for divisor in (0,-1,True,1<<31):
        try:costs([dict(type='average',count=1,divisor=divisor)],32)
        except ProtocolError as e:assert e.code=='AVERAGE_COUNT';invalid.append(str(divisor))
        else:raise AssertionError(divisor)
    result=dict(status='PASS_COORDINATOR_NO_SECRET_PARSE_ROLE_IO_ISOLATION',coordinator_reads=reads,opposite_role_rejections=failures,invalid_average_divisors=invalid,limitations='AST and runtime Python view checks, not OS sandbox or active security')
    target=ROOT/'results/application/role-views.json';target.write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()
