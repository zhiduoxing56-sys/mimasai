"""Owner-only sparse plaintext oracle; same ordered dot and once-only floor rules."""
import math
from .reference import Fixed
from .numerical import probability_reference,negative_log_reference

def sparse(a):return [[(j,v) for j,v in enumerate(row) if v] for row in a]
def trans(a,cols):
 out=[[] for _ in range(cols)]
 for i,row in enumerate(a):
  for j,v in row:out[j].append((i,v))
 return out

def multiply(a,b,cols,fx=None,audit=None,name='dot'):
 out=[];maxproduct=maxpartial=0
 for row in a:
  accum=[0]*cols
  for j,left in row:
   for col,right in b[j]:
    product=left*right
    if fx:fx.checked(product,name+' product')
    accum[col]+=product
    if fx:fx.checked(accum[col],name+' partial')
    maxproduct=max(maxproduct,abs(product));maxpartial=max(maxpartial,abs(accum[col]))
  out.append([v//fx.scale if fx else v for v in accum])
 if audit is not None:audit.append(dict(operation=name,max_abs_product=maxproduct,max_abs_partial_sum=maxpartial))
 return out

def step(p,x,w,labels,mask,fx=None,learning_rate=.5):
 n=len(x);features=len(w[0]);hidden=len(w[0][0]);classes=len(w[1][0]);s=fx.scale if fx else 1;count=sum(mask);audit=[];mm=lambda a,b,cols,name:multiply(a,b,cols,fx,audit,name)
 t0=mm(x,sparse(w[0]),hidden,'XW0');z0=mm(p,sparse(t0),hidden,'PT0');h=[[max(0,v) for v in row] for row in z0];t1=mm(sparse(h),sparse(w[1]),classes,'HW1');z1=mm(p,sparse(t1),classes,'PT1')
 if fx:prob,_=probability_reference(z1,fx.scale.bit_length()-1);loss=sum(negative_log_reference(prob[i][labels[i]],fx.scale.bit_length()-1) for i in range(n) if mask[i])//count
 else:
  prob=[];loss=0
  for i,row in enumerate(z1):
   ex=[math.exp(v-max(row)) for v in row];prob.append([v/sum(ex) for v in ex])
   if mask[i]:loss+=(max(row)+math.log(sum(ex))-row[labels[i]])/count
 d=[[(prob[i][j]-(s if j==labels[i] else 0))//count if fx else (prob[i][j]-int(j==labels[i]))/count for j in range(classes)] if mask[i] else [0]*classes for i in range(n)]
 dt1=mm(trans(p,n),sparse(d),classes,'dT1');dw1=mm(trans(sparse(h),hidden),sparse(dt1),classes,'dW1');dh=mm(sparse(dt1),trans(sparse(w[1]),classes),hidden,'dH');dz0=[[v if z>0 else 0 for v,z in zip(row,zrow)] for row,zrow in zip(dh,z0)];dt0=mm(trans(p,n),sparse(dz0),hidden,'dT0');dw0=mm(trans(x,features),sparse(dt0),hidden,'dW0')
 if fx:
  rate=round(learning_rate*s);nextw=[[[fx.checked(v-fx.checked(g*rate,'update product')//s,'update') for v,g in zip(row,grow)] for row,grow in zip(ww,gg)] for ww,gg in zip(w,[dw0,dw1])]
 else:nextw=[[[v-learning_rate*g for v,g in zip(row,grow)] for row,grow in zip(ww,gg)] for ww,gg in zip(w,[dw0,dw1])]
 return dict(transform0=t0,activation_input=z0,hidden=h,transform1=t1,logits=z1,probabilities=prob,loss=loss,logit_gradient=d,gradient0=dw0,gradient1=dw1,next_weights=nextw,backprop1=dt1,backprop_hidden=dh,backprop0=dt0),nextw,audit
