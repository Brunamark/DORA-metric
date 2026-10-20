import pandas as pd, numpy as np, sys, itertools, json
from scipy import stats
from sklearn.metrics import cohen_kappa_score
m=pd.read_csv(sys.argv[1],index_col=0)
out={}
def q(x): return x.quantile([.25,.5,.75]).round(3).tolist()
for c in ['freq_release','lt_a','lt_b','cfr_a','cfr_b','rec_h']:
    x=m[c].dropna(); out[c]=dict(n=len(x),q1=x.quantile(.25),med=x.median(),q3=x.quantile(.75))
    print(c,out[c])
# RQ05
for c in ['cfr_a','cfr_b']:
    d=m[['freq_release',c]].dropna(); rho,p=stats.spearmanr(d.freq_release,d[c]); print('RQ05',c,len(d),round(rho,3),p)
# Lead time a vs b
d=m[['lt_a','lt_b']].dropna(); print('lt a vs b spearman',stats.spearmanr(d.lt_a,d.lt_b)); 
print('wilcoxon',stats.wilcoxon(d.lt_a,d.lt_b)); print('a>b share',(d.lt_a>d.lt_b).mean(), 'ratio med', (d.lt_a/d.lt_b).median())
# RQ06
m['q_stars']=pd.qcut(m.stars,4,labels=['Q1','Q2','Q3','Q4']); m['q_contrib']=pd.qcut(m.contributors,4,labels=['Q1','Q2','Q3','Q4']); m['q_age']=pd.qcut(m.age_days,4,labels=['Q1','Q2','Q3','Q4'])
top=m.language.value_counts().index[:5]; m['lang']=np.where(m.language.isin(top),m.language,'Outras')
facs=['lang','q_stars','q_contrib','q_age']; mets=['freq_release','lt_a','cfr_b','cfr_a','rec_h']
rows=[]
for f,c in itertools.product(facs,mets):
    d=m[[f,c]].dropna(); g=[x[c].values for _,x in d.groupby(f,observed=True) if len(x)>=3]
    H,p=stats.kruskal(*g); n=len(d); rows.append(dict(fator=f,metrica=c,n=n,H=H,p=p,eps2=H/(n-1)))
t=pd.DataFrame(rows)
# Holm
o=t.p.sort_values().index; k=len(t); adj={}; run=0
for i,idx in enumerate(o):
    run=max(run,min(1,(k-i)*t.p[idx])); adj[idx]=run
t['p_holm']=pd.Series(adj); print(t.round(4).to_string()); t.to_csv('rq06_testes.csv',index=False)
# medianas por grupo
for f in facs:
    print(m.groupby(f,observed=True)[mets].median().round(3).assign(n=m.groupby(f,observed=True).size()))
# RQ07
cl=['C1','C2','C3','C4']
print(m[cl].apply(lambda s:s.value_counts()).fillna(0))
for a,b in itertools.combinations(cl,2):
    d=m[[a,b]].dropna(); print(a,b,len(d),'mudou%',round((d[a]!=d[b]).mean()*100,1),'kappa',round(cohen_kappa_score(d[a],d[b],weights='linear'),3))
# lead time: efeito de classificação por métrica
for s_ in ['s_freq','s_lta','s_cfrb','s_rec','s_cfra']: print(s_, m[s_].value_counts(normalize=True).sort_index().round(2).to_dict())
# negatives, sem commits
print('releases sem commits total',m.rel_sem_commits.sum(),'calc',m.rel_calc.sum(),'commits',m.commits.sum(),'neg',m.commits_neg.sum())
print('repos com >=1 commit neg',(m.commits_neg>0).sum())
print('cens',m.epis_cens.sum(),m.episodios.sum())
m.to_csv('metricas_enriquecido.csv')
