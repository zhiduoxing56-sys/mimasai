"""Public/authorized experimental evaluation; not an online protocol."""
from collections import Counter

def classification(labels,predictions,indices,classes):
    matrix=[[0]*classes for _ in range(classes)]
    for i in indices:matrix[labels[i]][predictions[i]]+=1
    rows=[]
    for c in range(classes):
        tp=matrix[c][c];support=sum(matrix[c]);selected=sum(row[c] for row in matrix);precision=tp/selected if selected else 0;recall=tp/support if support else 0
        rows.append(dict(class_index=c,support=support,predicted=selected,precision=precision,recall=recall,f1=2*precision*recall/(precision+recall) if precision+recall else 0))
    return dict(count=len(indices),accuracy=sum(matrix[j][j] for j in range(classes))/len(indices),confusion=matrix,classes=rows,macro_precision=sum(r['precision'] for r in rows)/classes,macro_recall=sum(r['recall'] for r in rows)/classes,macro_f1=sum(r['f1'] for r in rows)/classes,prediction_counts=dict(Counter(predictions[i] for i in indices)),missing_true_classes=[r['class_index'] for r in rows if not r['support']],macro_policy='All seven canonical classes, missing support has recall/F1 zero; support recorded explicitly')

def evaluate(data,prob):
    k=len(data['label_names']);labels=data['labels'];pred=[max(range(k),key=lambda j:row[j]) for row in prob];majority=min(range(k),key=lambda j:(-sum(labels[i]==j for i in data['splits']['train']),j))
    result={name:classification(labels,pred,ids,k) for name,ids in data['splits'].items()}
    for name,ids in data['splits'].items():
        local=min(range(k),key=lambda j:(-sum(labels[i]==j for i in ids),j));result[name]['training_majority_baseline']=classification(labels,[majority]*len(labels),ids,k);result[name]['split_majority_oracle']=dict(class_index=local,accuracy=sum(labels[i]==local for i in ids)/len(ids),scope='descriptive hindsight, never used as predictor or selection criterion');result[name]['nodes']=[dict(node_id=data['node_order'][i],label=labels[i],prediction=pred[i],probabilities=prob[i]) for i in ids]
    return result
