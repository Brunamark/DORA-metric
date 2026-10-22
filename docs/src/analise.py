import pandas as pd, numpy as np, sys, os, itertools, json
from scipy import stats
from sklearn.metrics import cohen_kappa_score
m=pd.read_csv(sys.argv[1],index_col=0)
OUT=os.path.dirname(os.path.abspath(sys.argv[1]))
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
t['p_holm']=pd.Series(adj); print(t.round(4).to_string()); t.to_csv(os.path.join(OUT,'rq06_testes.csv'),index=False)
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
m.to_csv(os.path.join(OUT,'metricas_enriquecido.csv'))
# ---------------------------------------------------------------------------
# Testes e contagens citados no RELATORIO.md (RQ01-RQ07)
print('\n=== Complementos do relatório ===')
f=m.freq_release.dropna()
print('RQ01 wilcoxon freq<1/sem', stats.wilcoxon(f-1,alternative='less').pvalue,
      'elite>=7',(f>=7).sum(),'>=1/sem',round((f>=1).mean(),3),'<1/mes',round((f<12/52.143).mean(),3))
a=m.cfr_a.dropna()
print('RQ03a n',len(a),'elite<=.15',(a<=.15).sum(),round((a<=.15).mean(),3),'>.45',(a>.45).sum(),
      'wilcoxon med>0.15 p',stats.wilcoxon(a-.15,alternative='greater').pvalue)
b=m.cfr_b.dropna()
print('RQ03b n',len(b),'zero',(b==0).sum(),'>.9',(b>.9).sum())
d=m[['cfr_a','cfr_b']].dropna()
print('RQ03 pareado n',len(d),'med a',round(d.cfr_a.median(),4),'med b',round(d.cfr_b.median(),4),
      'wilcoxon p',stats.wilcoxon(d.cfr_a,d.cfr_b).pvalue)
r=m.rec_h.dropna()
print('RQ04 n',len(r),'q',q(r),'<24h',round((r<24).mean(),3),'<1h',round((r<1).mean(),3),
      'wilcoxon med<24h p',stats.wilcoxon(r-24,alternative='less').pvalue)
print('RQ04 censura total',int(m.epis_cens.sum()),'de',int(m.episodios.sum()))
if 'epis_cens' in m:
    pc=(m.epis_cens/m.episodios).dropna()
    print('RQ04 proporcao censurada por repo: n',len(pc),'mediana',round(pc.median(),4),'p75',round(pc.quantile(.75),4),
          'p90',round(pc.quantile(.9),4),'max',round(pc.max(),4),'repos com >0',(pc>0).sum(),'repos >10%',(pc>.1).sum())
m['_rapido']=m.freq_release>=1
print('RQ05 cfr_b mediana freq>=1',m.loc[m._rapido,'cfr_b'].median(),'freq<1',m.loc[~m._rapido,'cfr_b'].median())
for c in ['cfr_a','rec_h']:
    d=m[['freq_release',c]].dropna(); print('RQ05',c,'n',len(d),stats.spearmanr(d.freq_release,d[c]))
d=m[['freq_release','cfr_a','q_age']].dropna()
for g,s in d.groupby('q_age',observed=True):
    print('RQ05 cfr_a por idade',g,len(s),stats.spearmanr(s.freq_release,s.cfr_a))
for x,y in itertools.combinations(cl,2):
    d=m[[x,y]].dropna(); k=int((d[x]!=d[y]).sum())
    print('RQ07 binomial',x,y,'n',len(d),'mudou',k,'p',stats.binomtest(k,len(d),.10,alternative='greater').pvalue)
# RQ06: tipo do projeto (rótulo da amostra-ouro, 60 repositórios)
ROT=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','validacao','rotulos_avaliacao_automatizada.csv')
if os.path.exists(ROT):
    tp=pd.read_csv(ROT,encoding='utf-8-sig').drop_duplicates('repo').set_index('repo')[['tipo_projeto']]
    mt=m.join(tp,how='inner'); rows=[]
    print('\nRQ06 tipo do projeto: n',len(mt),mt.tipo_projeto.value_counts().to_dict())
    for c in mets:
        d=mt[['tipo_projeto',c]].dropna(); H,p=stats.kruskal(*[x[c].values for _,x in d.groupby('tipo_projeto')])
        rows.append(dict(metrica=c,n=len(d),H=H,p=p,eps2=H/(len(d)-1)))
    t2=pd.DataFrame(rows); o=t2.p.sort_values().index; k=len(t2); run=0; adj={}
    for i,idx in enumerate(o): run=max(run,min(1,(k-i)*t2.p[idx])); adj[idx]=run
    t2['p_holm']=pd.Series(adj); print(t2.round(4).to_string())
    print(mt.groupby('tipo_projeto')[mets].median().round(3).assign(n=mt.groupby('tipo_projeto').size()))
