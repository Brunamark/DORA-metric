import pandas as pd, numpy as np, sys, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt, seaborn as sns
from scipy import stats
D,M,F=sys.argv[1],sys.argv[2],sys.argv[3]
m=pd.read_csv(M,index_col=0)
BL,OR,AQ,YE,MG,VI='#2a78d6','#eb6834','#1baf7a','#eda100','#e87ba4','#6250d6'
SEQ=['#86b6ef','#3987e5','#1c5cab','#0d366b']
INK,SEC,GRID='#0b0b0b','#52514e','#e4e3df'
plt.rcParams.update({'font.size':10,'axes.edgecolor':GRID,'axes.labelcolor':SEC,'xtick.color':SEC,'ytick.color':SEC,'axes.titlecolor':INK,'axes.titleweight':'bold','axes.titlesize':11,'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.color':GRID,'grid.linewidth':.6,'figure.dpi':140,'savefig.bbox':'tight','figure.facecolor':'#fcfcfb','axes.facecolor':'#fcfcfb'})
m['q_age']=pd.qcut(m.age_days,4,labels=['Q1 (mais novos)','Q2','Q3','Q4 (mais antigos)'])
top=m.language.value_counts().index[:5]; m['lang']=np.where(m.language.isin(top),m.language,'Outras')
order=['TypeScript','Python','Rust','Go','JavaScript','Outras']
def violin(ax,data,x,y,order,color,log=True,hl=None):
    d=data[[x,y]].dropna().copy(); 
    d['v']=np.log10(d[y]) if log else d[y]
    sns.violinplot(data=d,x=x,y='v',order=order,ax=ax,color=color,inner=None,cut=0,linewidth=.8,density_norm='width',saturation=1)
    for c in ax.collections: c.set_alpha(.45)
    sns.boxplot(data=d,x=x,y='v',order=order,ax=ax,width=.14,showfliers=False,boxprops=dict(facecolor='white',edgecolor=INK,linewidth=1),medianprops=dict(color=OR,linewidth=2),whiskerprops=dict(color=INK),capprops=dict(color=INK))
    sns.stripplot(data=d,x=x,y='v',order=order,ax=ax,color=INK,size=1.8,alpha=.35,jitter=.18)
    ax.set_xlabel('')
    if log:
        lo,hi=ax.get_ylim(); t=list(range(int(np.ceil(lo)),int(np.floor(hi))+1)); ax.set_yticks(t); ax.set_yticklabels([f'{10**v:g}' for v in t])
    ax.grid(axis='x',visible=False)
    return d
# FIG1 violinos DORA com faixas
fig,ax=plt.subplots(1,4,figsize=(14,4.6))
spec=[('freq_release','Frequência de deploy\n(releases/semana, n=350)',[(7,'Elite ≥7'),(1,'High ≥1'),(12/52.143,'Medium ≥1/mês')],BL),
      ('lt_a','Lead time (a) – mediana\n(dias, n=350)',[(1,'Elite <1d'),(7,'High <7d'),(30,'Medium <30d')],OR),
      ('cfr_a','CFR (a) – falha de CI\n(proporção, n=100)',[(.15,'Elite ≤15%'),(.30,'High ≤30%'),(.45,'Medium ≤45%')],AQ),
      ('rec_h','Tempo de recuperação – mediana\n(horas, n=95)',[(1,'Elite <1h'),(24,'High <1d'),(168,'Medium <1sem')],MG)]
for a,(c,t,lines,col) in zip(ax,spec):
    d=m[[c]].dropna().assign(g='')
    log=c!='cfr_a'
    v=np.log10(d[c]) if log else d[c]
    sns.violinplot(x=d.g,y=v,ax=a,color=col,inner=None,cut=0,linewidth=.8,saturation=1); 
    for k in a.collections: k.set_alpha(.45)
    sns.boxplot(x=d.g,y=v,ax=a,width=.12,showfliers=False,boxprops=dict(facecolor='white',edgecolor=INK),medianprops=dict(color=OR if col!=OR else BL,linewidth=2),whiskerprops=dict(color=INK),capprops=dict(color=INK))
    sns.stripplot(x=d.g,y=v,ax=a,color=INK,size=2,alpha=.35,jitter=.2)
    for val,lab in lines:
        yv=np.log10(val) if log else val
        a.axhline(yv,color=SEC,ls='--',lw=.8); a.text(.47,yv,lab,fontsize=7.5,color=SEC,va='bottom',ha='right',bbox=dict(fc='#fcfcfb',ec='none',pad=.5))
    a.set_title(t,fontsize=9.5); a.set_xlabel(''); a.set_ylabel(''); a.grid(axis='x',visible=False); a.set_xlim(-.5,.5)
    if log:
        lo,hi=a.get_ylim(); tk=list(range(int(np.ceil(lo)),int(np.floor(hi))+1)); a.set_yticks(tk); a.set_yticklabels([f'{10**x:g}' for x in tk])
fig.suptitle('Distribuição das quatro métricas DORA (violino + boxplot; eixo log, exceto CFR) com os cortes de classificação',fontweight='bold',y=1.02)
fig.savefig(f'{F}/fig01_violinos_dora.png'); plt.close()
# FIG2 lead time a vs b bolhas
fig,ax=plt.subplots(figsize=(6.6,6))
d=m[['lt_a','lt_b','rel_calc','age_days','rel_sem_commits']].dropna()
sc=ax.scatter(d.lt_b,d.lt_a,s=np.clip(d.rel_calc,4,600)*1.4+6,c=np.log10(d.age_days),cmap=matplotlib.colors.LinearSegmentedColormap.from_list('s',SEQ),alpha=.65,edgecolor='#fcfcfb',linewidth=.8)
lim=[1e-3,6e3]; ax.plot(lim,lim,color=SEC,ls='--',lw=1); ax.set_xscale('log'); ax.set_yscale('log'); ax.set_xlim(lim); ax.set_ylim(lim)
ax.text(2e-3,1e1,'(a) > (b): commit antigo\n"esquecido" infla (a)',fontsize=8,color=SEC); ax.text(2e1,3e-3,'(b) > (a)',fontsize=8,color=SEC)
ax.set_xlabel('Lead time (b) – mediana por commit (dias)'); ax.set_ylabel('Lead time (a) – mediana por release (dias)')
ax.set_title('Lead time: variante (a) × (b)\nbolha = nº de releases calculadas · cor = idade do repositório')
cb=fig.colorbar(sc,ax=ax,shrink=.7); cb.set_label('log10(idade em dias)')
fig.savefig(f'{F}/fig02_bolhas_leadtime_a_b.png'); plt.close()
# FIG3 violinos por idade
fig,ax=plt.subplots(1,3,figsize=(14,4.4)); qo=list(m.q_age.cat.categories)
for a,(c,t,col,lg) in zip(ax,[('freq_release','Frequência de deploy (releases/semana)',BL,True),('lt_a','Lead time (a) (dias)',OR,True),('cfr_b','CFR (b) – release seguida de patch ≤7d',AQ,False)]):
    violin(a,m,'q_age',c,qo,col,log=lg); a.set_title(t); a.set_ylabel(''); a.tick_params(axis='x',labelsize=8)
fig.suptitle('Métricas DORA por quartil de idade do repositório',fontweight='bold',y=1.02); fig.savefig(f'{F}/fig03_violinos_idade.png'); plt.close()
# FIG4 violinos por linguagem
fig,ax=plt.subplots(1,3,figsize=(14,4.4))
for a,(c,t,col,lg) in zip(ax,[('lt_a','Lead time (a) (dias)',OR,True),('cfr_b','CFR (b)',AQ,False),('freq_release','Frequência de deploy (releases/semana)',BL,True)]):
    violin(a,m,'lang',c,order,col,log=lg); a.set_title(t); a.set_ylabel(''); a.tick_params(axis='x',labelsize=8,rotation=20)
fig.suptitle('Métricas DORA por linguagem principal',fontweight='bold',y=1.02); fig.savefig(f'{F}/fig04_violinos_linguagem.png'); plt.close()
# proximidade
r=pd.read_csv(f'{D}/releases.csv',parse_dates=['published_at'])
INI=pd.Timestamp('2025-10-01',tz='UTC'); FIM=pd.Timestamp('2026-10-01 23:59:59',tz='UTC')
rel=r[(r.published_at>=INI)&(r.published_at<=FIM)&(~r.prerelease)]
pa={}
for n,g in rel.groupby('full_name'):
    t=np.sort(g.published_at.values.astype('datetime64[s]').astype('int64'))
    ev=t[t<=FIM.value//10**9-7*86400]
    if len(ev)<5: continue
    nxt=np.searchsorted(t,ev,side='right'); ok=(nxt<len(t))&(t[np.minimum(nxt,len(t)-1)]-ev<=7*86400)
    pa[n]=ok.mean()
m['seguida_7d']=pd.Series(pa); m['frac_patch']=m.cfr_b/m.seguida_7d
m.to_csv(M.replace('.csv','_2.csv'))
# FIG5 bolhas RQ05
fig,ax=plt.subplots(1,2,figsize=(14,5.4))
cmap=dict(zip(qo,SEQ))
for a,c,t in [(ax[0],'cfr_a','(a) Proxy de CI (n=100)'),(ax[1],'cfr_b','(b) Proxy de entrega (n=344)')]:
    d=m[['freq_release',c,'stars','q_age']].dropna(); rho,p=stats.spearmanr(d.freq_release,d[c])
    for q in qo:
        s=d[d.q_age==q]; a.scatter(s.freq_release,s[c],s=np.sqrt(s.stars)*.9,c=cmap[q],alpha=.7,edgecolor='#fcfcfb',linewidth=.8,label=q)
    a.set_xscale('log'); a.set_xlabel('Frequência de deploy (releases/semana, escala log)'); a.set_ylabel('CFR'); a.set_title(f'CFR {t}\nSpearman ρ = {rho:.2f}  (p = {p:.1g})')
    if c=='cfr_b':
        x=np.logspace(-1.1,1.5,100); a.plot(x,1-np.exp(-x),color=OR,lw=2,ls='--',label='teto "por acaso": 1−e^(−freq)'); a.set_ylim(-.03,1.05)
    else: a.set_ylim(-.03,1)
    a.legend(title='Idade (quartil) · bolha = estrelas',fontsize=7.5,title_fontsize=8,loc='upper left')
fig.suptitle('Velocidade × estabilidade (RQ05)',fontweight='bold',y=1.01); fig.savefig(f'{F}/fig05_bolhas_freq_cfr.png'); plt.close()
# FIG6 recuperação por episódio
e=pd.read_csv(f'{D}/episodios.csv'); e=e[~e.censurado].merge(m[['lang']],left_on='full_name',right_index=True)
e['v']=np.log10(e.duracao_horas.clip(lower=1/360))
fig,ax=plt.subplots(figsize=(9,4.6))
sns.violinplot(data=e,x='lang',y='v',order=order,ax=ax,color=MG,inner=None,cut=0,linewidth=.8,density_norm='width',saturation=1)
for c in ax.collections: c.set_alpha(.45)
sns.boxplot(data=e,x='lang',y='v',order=order,ax=ax,width=.12,showfliers=False,boxprops=dict(facecolor='white',edgecolor=INK),medianprops=dict(color=BL,linewidth=2),whiskerprops=dict(color=INK),capprops=dict(color=INK))
for val,lab in [(1,'1 h'),(24,'1 dia'),(168,'1 semana')]:
    ax.axhline(np.log10(val),color=SEC,ls='--',lw=.8); ax.text(5.45,np.log10(val),lab,fontsize=8,color=SEC,va='bottom',ha='right')
lo,hi=ax.get_ylim(); tk=list(range(int(np.ceil(lo)),int(np.floor(hi))+1)); ax.set_yticks(tk); ax.set_yticklabels([f'{10**v:g}' for v in tk]); ax.set_xlabel(''); ax.set_ylabel('Duração do episódio de falha (horas, log)'); ax.grid(axis='x',visible=False)
ax.set_title('Tempo de recuperação por episódio de falha de CI, por linguagem (n = %d episódios)'%len(e)); fig.savefig(f'{F}/fig06_violino_recuperacao.png'); plt.close()
e.groupby('lang').duracao_horas.agg(['count','median']).to_csv('/home/claude/work/rec_episodios_lang.csv')
print('episodios total',len(e),'mediana',e.duracao_horas.median(),'p25',e.duracao_horas.quantile(.25),'p75',e.duracao_horas.quantile(.75),'p90',e.duracao_horas.quantile(.9), 'frac<1h',(e.duracao_horas<1).mean(), '>24h',(e.duracao_horas>24).mean())
# FIG7 matriz de bolhas RQ07
lab={1:'Low',2:'Medium',3:'High',4:'Elite'}
fig,ax=plt.subplots(1,3,figsize=(14,4.8))
for a,(x,y) in zip(ax,[('C1','C2'),('C1','C3'),('C1','C4')]):
    d=m[[x,y]].dropna().astype(int); ct=pd.crosstab(d[x],d[y]).reindex(index=[1,2,3,4],columns=[1,2,3,4],fill_value=0)
    for i in range(1,5):
        for j in range(1,5):
            n=ct.loc[i,j]
            if n: a.scatter(j,i,s=n*28,color=BL if i==j else OR,alpha=.6,edgecolor='#fcfcfb'); a.text(j,i,str(n),ha='center',va='center',fontsize=9,color=INK)
    a.set_xticks([1,2,3,4]); a.set_yticks([1,2,3,4]); a.set_xticklabels([lab[i] for i in range(1,5)]); a.set_yticklabels([lab[i] for i in range(1,5)]); a.set_xlim(.4,4.6); a.set_ylim(.4,4.6)
    a.plot([.4,4.6],[.4,4.6],color=SEC,ls=':',lw=.8); a.set_xlabel(y); a.set_ylabel(x+' (referência)'); mu=(d[x]!=d[y]).mean()*100; a.set_title(f'{x} × {y}: {mu:.0f}% mudaram de categoria (n={len(d)})',fontsize=9.5)
fig.suptitle('Análise de sensibilidade (RQ07): categoria DORA geral por combinação · azul = igual, laranja = mudou',fontweight='bold',y=1.02); fig.savefig(f'{F}/fig07_bolhas_sensibilidade.png'); plt.close()
# números extras
d=m[['freq_release','cfr_b','seguida_7d','frac_patch']].dropna()
print('seguida_7d med',d.seguida_7d.median(),'frac_patch med',d.frac_patch.median())
print('spearman freq x seguida7d',stats.spearmanr(d.freq_release,d.seguida_7d))
print('spearman freq x frac_patch',stats.spearmanr(d.freq_release,d.frac_patch.fillna(0)))
for q in qo:
    s=m[m.q_age==q][['freq_release','cfr_b']].dropna(); print(q,len(s),stats.spearmanr(s.freq_release,s.cfr_b))
print((m.cfr_b>.9).sum(),(m.cfr_b>.5).sum())
d=m[['freq_release','cfr_a','q_age']].dropna()
for q in qo:
    s=d[d.q_age==q]; print('cfra',q,len(s),stats.spearmanr(s.freq_release,s.cfr_a)[0])
print('CFR a repos >0.45',(m.cfr_a>.45).sum(), 'cfr_a<=.15',(m.cfr_a<=.15).sum())
print('freq: <1/mo',(m.freq_release<12/52.143).mean(),'>=1/sem',(m.freq_release>=1).mean(),'>=7',(m.freq_release>=7).sum())
print('lt<1d',(m.lt_a<1).mean(),'>=30d',(m.lt_a>=30).mean())
