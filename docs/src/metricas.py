import pandas as pd, numpy as np, re, sys
D=sys.argv[1]; OUT=sys.argv[2]
r=pd.read_csv(f'{D}/releases.csv',parse_dates=['published_at'])
s=pd.read_csv(f'{D}/repos_selecionados.csv')
w=pd.read_csv(f'{D}/workflow_runs_repos.csv')
l=pd.read_csv(f'{D}/lead_time_repos.csv')
e=pd.read_csv(f'{D}/episodios.csv')
INI=pd.Timestamp('2025-10-01',tz='UTC'); FIM=pd.Timestamp('2026-10-01 23:59:59',tz='UTC')
SEM=365/7
rw=r[(r.published_at>=INI)&(r.published_at<=FIM)&(~r.draft)]
rel=rw[~rw.prerelease]
m=s[['full_name','stars','language','contributors','age_days']].copy().set_index('full_name')
m['freq_release']=rel.groupby('full_name').size()/SEM
m['freq_release_pre']=rw.groupby('full_name').size()/SEM
m['n_prerelease']=rw[rw.prerelease].groupby('full_name').size(); m['n_prerelease']=m.n_prerelease.fillna(0)
l=l.set_index('full_name')
m['lt_a']=l.lead_time_release_mediana_dias; m['lt_b']=l.lead_time_commit_mediana_dias
m['commits']=l.commits; m['rel_sem_commits']=l.releases_sem_commits; m['rel_calc']=l.releases_calculadas
m['commits_neg']=l.commits_lead_time_negativo
# CFR (b)
pat=re.compile(r'^(?P<pre>.*?)[vV]?(?P<M>\d+)\.(?P<m>\d+)(?:\.(?P<p>\d+))?')
def parse(t):
    x=pat.match(str(t))
    if not x: return None
    return (x['pre'].strip().lower(),int(x['M']),int(x['m']),int(x['p']) if x['p'] else 0)
cfr={}
for name,g in rel.groupby('full_name'):
    g=g.sort_values('published_at').reset_index(drop=True)
    v=[parse(t) for t in g.tag_name]
    n_av=0; n_fail=0; n_unparsed=sum(x is None for x in v)
    for i in range(len(g)):
        if v[i] is None: continue
        if g.published_at[i]>FIM-pd.Timedelta(days=7): continue
        n_av+=1
        for j in range(i+1,len(g)):
            if (g.published_at[j]-g.published_at[i])>pd.Timedelta(days=7): break
            if v[j] and v[j][0]==v[i][0] and v[j][1:3]==v[i][1:3] and v[j][3]>v[i][3]:
                n_fail+=1; break
    cfr[name]=(n_av,n_fail,n_unparsed)
c=pd.DataFrame(cfr,index=['rel_avaliadas','rel_falha_b','rel_sem_semver']).T
m=m.join(c)
m['cfr_b']=np.where(m.rel_avaliadas>=5,m.rel_falha_b/m.rel_avaliadas,np.nan)
m['rework']=m.cfr_b  # mesma heurística
# CI
w=w.set_index('full_name')
m['cfr_a']=w.cfr_a; m['runs_validos']=w.runs_sucesso+w.runs_falha
m['rec_h']=e[~e.censurado].groupby('full_name').duracao_horas.median()
m.loc[~m.index.isin(w.index),['rec_h']]=np.nan
m['tem_ci']=m.index.isin(w.index)
m['episodios']=e.groupby('full_name').size()
m['epis_cens']=e.groupby('full_name').censurado.sum()
# DORA
def sc_freq(x): return np.where(x>=7,4,np.where(x>=1,3,np.where(x>=12/52.143,2,1)))  # >=1/mês ~ 12/52 sem
def sc_lt(x): return np.where(x<1,4,np.where(x<7,3,np.where(x<30,2,1)))
def sc_cfr(x): return np.where(x<=.15,4,np.where(x<=.30,3,np.where(x<=.45,2,1)))
def sc_rec(x): return np.where(x<1/24,4,np.where(x<1,3,np.where(x<7,2,1)))
def sc(fn,x): 
    return pd.Series(np.where(pd.isna(x),np.nan,fn(x.fillna(0))),index=x.index)
m['s_freq']=sc(sc_freq,m.freq_release); m['s_freq_pre']=sc(sc_freq,m.freq_release_pre)
m['s_lta']=sc(sc_lt,m.lt_a); m['s_ltb']=sc(sc_lt,m.lt_b)
m['s_cfra']=sc(sc_cfr,m.cfr_a); m['s_cfrb']=sc(sc_cfr,m.cfr_b)
m['s_rec']=sc(sc_rec,m.rec_h/24)
def geral(cols):
    return np.floor(m[cols].median(axis=1,skipna=False))
m['C1']=geral(['s_freq','s_lta','s_cfra','s_rec'])
m['C2']=geral(['s_freq_pre','s_ltb','s_cfrb','s_rec'])
m['C3']=geral(['s_freq','s_ltb','s_cfra','s_rec'])
m['C4']=geral(['s_freq','s_lta','s_cfrb','s_rec'])
m.to_csv(OUT)
print(m.describe().T.to_string())
