import pandas as pd, json, math
import os; SP=os.path.dirname(os.path.abspath(__file__))+'/'
# Official NFL per-team salary cap ($M). 2010 was uncapped; 2009 figure used as a stand-in.
CAP={2000:62.172,2001:67.405,2002:71.101,2003:75.007,2004:80.582,2005:85.5,2006:102.0,2007:109.0,2008:116.0,
     2009:123.0,2010:123.0,2011:120.0,2012:120.6,2013:123.0,2014:133.0,2015:143.28,2016:155.27,2017:167.0,
     2018:177.2,2019:188.2,2020:198.2,2021:182.5,2022:208.2,2023:224.8,2024:255.4,2025:279.2,2026:301.2}
TEAMS={y:(31 if y<2002 else 32) for y in CAP}
d=pd.read_parquet(SP+'contracts.parquet'); q=d[d.position=='QB'].copy()
q['pid']=q.otc_id.astype(str)
names=q.groupby('pid').player.first()
# contracts
cons=q[['pid','player','team','year_signed','years','value','apy','guaranteed']].dropna(subset=['year_signed','years'])
cons=cons[(cons.year_signed+cons.years-1>=2000)&(cons.years>0)]
# season cap hits
hist=[]
for pid,g in q.groupby('pid'):
    sh=g.iloc[0].season_history
    if sh is None: continue
    for s in sh:
        y=s.get('year')
        if y and str(y).isdigit() and 2000<=int(y)<=2026 and s.get('cap_number') is not None:
            hist.append(dict(pid=pid,season=int(y),team=s['team'],cap_hit=s['cap_number']))
h=pd.DataFrame(hist)
h=h.groupby(['pid','season'],as_index=False).agg(team=('team','last'),cap_hit=('cap_hit','sum'))
# contract APY in force: latest-signed deal with year_signed<=season<year_signed+years,
# breaking same-year ties toward the team the player was rostered by. If that deal is clearly
# with another team, a deal with the roster team signed the same year or later replaces it
# (e.g. a reworked contract after a trade).
def inforce(r):
    mine=cons[(cons.pid==r.pid)&(cons.year_signed<=r.season)]
    c=mine[mine.year_signed+mine.years>r.season]
    if c.empty: return pd.Series([None,None])
    # multi-team labels like "DEN/KC" use abbreviations, so treat them as a possible match
    same=lambda t: t==r.team or '/' in t
    c=c.assign(same_team=c.team.map(same)).sort_values(['year_signed','same_team','apy']).iloc[-1]
    if not same(c.team):
        alt=mine[(mine.team==r.team)&(mine.year_signed>=c.year_signed)]
        if not alt.empty: c=alt.sort_values(['year_signed','apy']).iloc[-1]
    return pd.Series([c.apy,int(c.year_signed)])
h[['apy','signed']]=h.apply(inforce,axis=1)
h['player']=h.pid.map(names)
h['cap']=h.season.map(CAP)
h=h[h.cap_hit>0]
h['hit_pct']=h.cap_hit/h.cap; h['apy_pct']=h.apy/h.cap
# overall
rows=[]
for y,g in h.groupby('season'):
    pool=TEAMS[y]*CAP[y]
    top=g.sort_values('cap_hit').groupby('team').tail(1)
    topa=g.dropna(subset=['apy']).sort_values('apy').groupby('team').tail(1)
    rows.append(dict(season=y,cap=CAP[y],teams=TEAMS[y],n_qbs=len(g),n_contracts=int(g.apy.notna().sum()),
        sum_apy=round(g.apy.sum(),3),sum_hit=round(g.cap_hit.sum(),3),
        apy_pct=g.apy.sum()/pool,hit_pct=g.cap_hit.sum()/pool,
        top_apy_pct=topa.apy.sum()/pool,top_hit_pct=top.cap_hit.sum()/pool,n_teams_hit=len(top),n_teams_apy=len(topa)))
ov=pd.DataFrame(rows); print(ov.round(4).to_string())
h.to_csv(SP+'qb_seasons.csv',index=False); ov.to_csv(SP+'qb_overall.csv',index=False)
cons['cap_at_sign']=cons.year_signed.map(lambda y: CAP.get(int(y)))
cons['apy_pct_at_sign']=cons.apy/cons.cap_at_sign
cons.to_csv(SP+'qb_contracts.csv',index=False)
