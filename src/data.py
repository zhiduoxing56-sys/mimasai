"""Owner-side public Cora import. Never imported by an online worker."""
import collections,hashlib,io,json,math,tarfile,urllib.request
from pathlib import Path
from .reference import ROOT,config,graph

def cora(archive=None,download=False,*,node_count=None,full_graph=False):
    c=config();spec=c['data_experiment'];count=2708 if full_graph else spec['nodes'] if node_count is None else node_count
    if type(count)!=int or not 16<=count<=2708:raise ValueError('public experiment node count')
    p=Path(archive) if archive else ROOT/'deps/downloads/cora.tgz'
    if not p.exists():
        if not download:raise FileNotFoundError('Use --download or --archive for the hash-locked original Cora archive')
        p.parent.mkdir(parents=True,exist_ok=True)
        with urllib.request.urlopen(spec['url'],timeout=60) as r:data=r.read(2000000)
        if hashlib.sha256(data).hexdigest()!=spec['sha256']:raise ValueError('Cora download digest')
        p.write_bytes(data)
    data=p.read_bytes()
    if hashlib.sha256(data).hexdigest()!=spec['sha256']:raise ValueError('Cora archive digest')
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as t:
        files={m.name:m for m in t.getmembers() if m.isfile()}
        if set(files)!={'cora/README','cora/cora.content','cora/cora.cites'}:raise ValueError('archive member set')
        content=t.extractfile(files['cora/cora.content']).read().decode();citations=t.extractfile(files['cora/cora.cites']).read().decode()
    names=spec['labels'];nodes={}
    for line in content.splitlines():
        fields=line.split();ident=fields[0]
        if len(fields)!=1435 or ident in nodes or fields[-1] not in names or any(v not in ('0','1') for v in fields[1:-1]):raise ValueError('Cora content row')
        nodes[ident]=(list(map(int,fields[1:-1])),names.index(fields[-1]))
    if len(nodes)!=2708:raise ValueError('node count')
    edges=[];adj={v:set() for v in nodes}
    for line in citations.splitlines():
        u,v=line.split()
        if u not in nodes or v not in nodes or u==v:raise ValueError('citation endpoints/self-loop')
        edges.append((u,v));adj[u].add(v);adj[v].add(u)
    anchor=min(nodes,key=int);queue=collections.deque([anchor]);seen={anchor};order=[]
    while queue and len(order)<count:
        u=queue.popleft();order.append(u)
        for v in sorted(adj[u],key=int):
            if v not in seen:seen.add(v);queue.append(v)
    if full_graph:order=sorted(nodes,key=int)
    elif len(order)!=count:raise ValueError('BFS component too small')
    index={u:i for i,u in enumerate(order)};selected=[(index[u],index[v],1.0) for u,v in edges if u in index and v in index]
    columns=[j for j in range(1433) if any(nodes[u][0][j] for u in order)]
    features=[]
    for u in order:
        words=nodes[u][0];norm=math.sqrt(sum(words))
        if not norm:raise ValueError('empty feature row')
        features.append([words[j]/norm for j in columns])
    ranked=sorted(range(len(order)),key=lambda i:hashlib.sha256((spec['split_salt']+order[i]).encode()).digest())
    train_count=spec['full_reference_train_nodes'] if full_graph else count//2;validation_count=spec['full_reference_validation_nodes'] if full_graph else count//4
    if not full_graph and count not in (16,32,64):raise ValueError('supported fixed public split scales: 16,32,64')
    splits=dict(train=ranked[:train_count],validation=ranked[train_count:train_count+validation_count],test=ranked[train_count+validation_count:]);g=dict(c['graph_reference'],nodes=len(order),node_order=order,features=features,undirected_edges=selected)
    if full_graph:
        adjacency=[{} for _ in order]
        for u,v,weight in selected:adjacency[u][v]=adjacency[u].get(v,0)+weight;adjacency[v][u]=adjacency[v].get(u,0)+weight
        for i in range(count):adjacency[i][i]=1.0
        degree=[sum(row.values()) for row in adjacency];propagation=[[(j,weight/math.sqrt(degree[i]*degree[j])) for j,weight in sorted(row.items())] for i,row in enumerate(adjacency)]
    else:_,degree,propagation=graph(g)
    return dict(source_url=spec['url'],archive_sha256=spec['sha256'],full_nodes=len(nodes),full_citation_records=len(edges),node_order=order,feature_columns=columns,features=features,labels=[nodes[u][1] for u in order],label_names=names,splits=splits,edges=selected,degrees=degree,propagation=propagation,preprocessing=['Full graph in numeric node-ID order' if full_graph else 'Smallest numeric paper ID, FIFO BFS, numeric sorted neighbors; no label-dependent selection','Full original graph, sparse storage' if full_graph else 'Induced subgraph, not full-graph target equivalence','Citation records made undirected; reciprocal/duplicate weights summed','One unit self-loop then symmetric normalization','Remove all-zero columns (lossless on this subgraph), row L2 normalize words',f'Fixed public-ID hash split, {train_count} train / {validation_count} validation / {count-train_count-validation_count} test'],privacy='Public benchmark owner-side plaintext preparation assumption; no private normalization',license='Original archive README contains no explicit redistribution license; data excluded from Git/review bundle')
