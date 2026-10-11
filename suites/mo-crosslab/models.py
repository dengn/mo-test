"""Native pandas feature pipelines and NumPy/SciPy scientific decision chains."""
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from graphs import QUESTIONS,params

CF=['credit','n_orders','acquisition','outstanding','units','late','pending','variety','momentum','tickets','handling','csat','reopened','sessions','depth','arrears','active_months','deferred_revenue','baseline','peer_credit','recency']
PF=['price','sale_price','promo_rate','stockout_rate','rolling_units','buyers','late','vibration','failures','downtime','energy_cost','carbon','on_hand','lead_days','unit_cost','fill_rate','delay','macro_return','country_cost','marketing_spend']

def plain(x):
    if isinstance(x,dict):return {str(k):plain(v) for k,v in x.items()}
    if isinstance(x,(list,tuple,np.ndarray)):return [plain(v) for v in x]
    if isinstance(x,np.generic):return x.item()
    return x

def feature_numpy(frame,domain,train):
    cols=CF if domain=='customer' else PF
    raw=np.asarray(frame[cols],dtype=float);med=np.median(raw[train],axis=0)
    scale=np.maximum(np.median(np.abs(raw[train]-med),axis=0)*1.4826,.001)
    z=np.clip((raw-med)/scale,-8,8)
    # Interaction basis represents support burden, demand/inventory and price/supply interactions.
    interactions=np.column_stack([z[:,0]*z[:,1],z[:,2]*z[:,3],z[:,4]*z[:,5],z[:,6]*z[:,7]])
    return np.column_stack([z,interactions]),med,scale

def feature_pandas(frame,domain,train):
    cols=CF if domain=='customer' else PF
    # Entity lookup, validated merge, aligned robust transforms and cross-feature pivot.
    key='cid' if domain=='customer' else 'pid'
    block=frame[[key]+cols].set_index(key)
    reference=block.iloc[np.flatnonzero(train)]
    median=reference.median();scale=(reference.sub(median).abs().median()*1.4826).clip(lower=.001)
    z=block.sub(median).div(scale).clip(-8,8)
    ids=frame[[key]].merge(z.reset_index(),on=key,how='left',validate='one_to_one')
    zz=ids[cols]
    interactions=pd.DataFrame({f'cross{k}':zz.iloc[:,2*k]*zz.iloc[:,2*k+1] for k in range(4)},index=zz.index)
    return pd.concat([zz,interactions],axis=1).to_numpy(),median.to_numpy(),scale.to_numpy()

def sigmoid(x):return 1/(1+np.exp(-np.clip(x,-35,35)))

def pca_cluster(x,groups,seed):
    centered=x-x.mean(0);cov=centered.T@centered/max(1,len(x)-1)
    vals,vec=np.linalg.eigh(cov);pcs=centered@vec[:,-min(6,x.shape[1]):]
    # Eigenvector signs are canonicalized before deterministic centroids are chosen.
    for j in range(pcs.shape[1]):
        col=vec[:,-pcs.shape[1]+j];pcs[:,j]*=1 if col[np.argmax(abs(col))]>=0 else -1
    rng=np.random.default_rng(seed);centers=pcs[rng.choice(len(pcs),groups,replace=False)].copy();labels=np.zeros(len(x),int)
    for _ in range(30):
        distance=((pcs[:,None]-centers[None,:])**2).sum(2);labels=distance.argmin(1)
        newer=np.vstack([pcs[labels==g].mean(0) if np.any(labels==g) else centers[g] for g in range(groups)])
        if np.max(abs(newer-centers))<1e-8:break
        centers=newer
    return labels,pcs,vals,centers

def calculate(f,frame,i,backend='numpy'):
    domain,key,_=QUESTIONS[f];p=params(i);idcol='cid' if domain=='customer' else 'pid'
    df=frame.astype(float).round(8)
    ids=df[idcol].to_numpy(int);group=df['region' if domain=='customer' else 'category'].to_numpy(int)
    train=ids%5!=p['holdout'];test=~train
    x,median,scale=(feature_pandas if backend=='pandas' else feature_numpy)(df,domain,train)
    nx,mn,sn=feature_numpy(df,domain,train)
    checks={'unique_entities':len(np.unique(ids))==len(ids),'native_feature_equivalence':bool(np.allclose(x,nx,rtol=1e-12,atol=1e-12)),
            'heldout_entities_disjoint':not bool(set(ids[train])&set(ids[test])),'nonempty_train_test':bool(train.any() and test.any())}
    x=np.round(nx,10)
    cov=np.cov(x[train],rowvar=False);cov=.85*cov+.15*np.diag(np.diag(cov))+np.eye(x.shape[1])*1e-6
    eig=np.linalg.eigvalsh(cov);checks['shrinkage_covariance_psd']=bool(eig.min()>0)
    base=df['margin'].to_numpy(float);target=base if domain=='customer' else df.demand.to_numpy(float)
    metrics={'entities':len(ids),'train':int(train.sum()),'test':int(test.sum()),'feature_dimensions':x.shape[1],
             'covariance_trace':float(np.trace(cov)),'min_eigenvalue':float(eig.min())}
    diagnostics={'feature_median':median,'feature_scale':scale,'covariance':cov}
    allocation=np.zeros(len(ids));benefit=np.zeros(len(ids));rng=np.random.default_rng(p['seed']+f*10000)
    branch=f%10
    if f in [0,10,18]:
        y=target if f!=18 else np.log1p(np.maximum(df.demand,0).to_numpy())
        # Iteratively reweighted Huber ridge, followed by held-out evaluation and bootstrap stability.
        z=np.column_stack([np.ones(len(x)),x]);zt=z[train];yt=y[train];pen=np.eye(z.shape[1])*p['ridge'];pen[0,0]=0
        w=np.ones(len(yt));coef=np.zeros(z.shape[1])
        for _ in range(15):
            coef=np.linalg.solve(zt.T@(w[:,None]*zt)+pen,zt.T@(w*yt));res=yt-zt@coef
            delta=max(.01,float(np.median(abs(res))*1.4826)*1.35);w=np.minimum(1,delta/np.maximum(abs(res),1e-9))
        pred=z@coef;boot=[]
        for _ in range(24):
            sel=rng.integers(0,len(yt),len(yt));zb=zt[sel];yb=yt[sel]
            cb=np.linalg.solve(zb.T@zb+pen,zb.T@yb);boot.append(z[test]@cb)
        lo,hi=np.quantile(boot,[.025,.975],axis=0)
        metrics.update(holdout_rmse=float(np.sqrt(np.mean((pred[test]-y[test])**2))),holdout_mae=float(np.mean(abs(pred[test]-y[test]))),bootstrap_width=float(np.mean(hi-lo)))
        diagnostics.update(coefficients=coef,bootstrap_lower=lo,bootstrap_upper=hi)
        allocation=pred;benefit=y-pred;checks['bootstrap_intervals_ordered']=bool(np.all(hi>=lo))
    elif f==2:
        # As-of default outcome never enters the input basis; customer-separated calibration.
        y=df.defaulted.to_numpy(float);z=np.column_stack([np.ones(len(x)),x]);coef=np.zeros(z.shape[1]);pen=np.eye(z.shape[1])*p['ridge'];pen[0,0]=.001
        for _ in range(35):
            prob=sigmoid(z[train]@coef);v=np.maximum(prob*(1-prob),1e-5)
            grad=z[train].T@(prob-y[train])+pen@coef;h=z[train].T@(v[:,None]*z[train])+pen
            step=np.linalg.solve(h,grad);coef-=np.clip(step,-2,2)
            if np.max(abs(step))<1e-8:break
        prob=sigmoid(z@coef);metrics.update(brier=float(np.mean((prob[test]-y[test])**2)),log_loss=float(-np.mean(y[test]*np.log(prob[test]+1e-12)+(1-y[test])*np.log(1-prob[test]+1e-12))))
        diagnostics.update(coefficients=coef,group_calibration={int(g):float(np.mean(prob[test&(group==g)]-y[test&(group==g)])) for g in np.unique(group) if np.any(test&(group==g))})
        allocation=prob;benefit=prob*df.balance.to_numpy();checks['risk_probability_bounds']=bool(np.all((prob>=0)&(prob<=1)))
    elif f in [3,13]:
        # Graph links represent shared region/credit proximity or supplier country/category.
        distance=((x[:,:6,None]-x[:,:6].T[None,:,:])**2).sum(1)
        link=(group[:,None]==group[None,:])*np.exp(-np.minimum(distance,50)/12);np.fill_diagonal(link,0)
        transition=link/np.maximum(link.sum(1,keepdims=True),1e-12)
        shock=(df.overdue.to_numpy()/np.maximum(df.balance.to_numpy(),1) if domain=='customer' else 1-df.fill_rate.to_numpy())
        propagated=shock.copy()
        for iteration in range(80):
            newer=(1-p['risk'])*shock+p['risk']*(transition@propagated)
            if np.max(abs(newer-propagated))<1e-10:break
            propagated=newer
        residual=np.max(abs(propagated-((1-p['risk'])*shock+p['risk']*(transition@propagated))))
        metrics.update(graph_edges=int((link>0).sum()),fixed_point_residual=float(residual),iterations=iteration+1)
        allocation=propagated;benefit=propagated*(df.balance.to_numpy() if domain=='customer' else df.sold.to_numpy())
        checks['diffusion_fixed_point']=bool(residual<1e-7);checks['row_stochastic']=bool(np.allclose(transition.sum(1),1))
    elif f in [4,8,15]:
        labels,pcs,vals,centers=pca_cluster(x,4+i%3,p['seed']);diagnostics.update(pca_variance=vals,cluster_centers=centers)
        if f in [8,15]:
            k=4+i%3;mu=centers.copy();var=np.full((k,pcs.shape[1]),max(.1,float(pcs.var())));weight=np.full(k,1/k)
            for _ in range(35):
                logp=-.5*((pcs[:,None]-mu)**2/var+np.log(2*np.pi*var)).sum(2)+np.log(weight+1e-12)
                ll=logp.max(1,keepdims=True);r=np.exp(logp-ll);r/=r.sum(1,keepdims=True)
                mass=r.sum(0)+1e-9;mu=r.T@pcs/mass[:,None]
                var=np.maximum((r[:,:,None]*(pcs[:,None]-mu)**2).sum(0)/mass[:,None],.001);weight=mass/mass.sum()
            labels=r.argmax(1);metrics['mixture_entropy']=float(np.mean(-np.sum(r*np.log(r+1e-12),axis=1)))
            diagnostics.update(mixture_weights=weight,mixture_centers=mu,mixture_variances=var);checks['posterior_probability_conservation']=bool(np.allclose(r.sum(1),1))
        allocation=labels.astype(float);benefit=np.sqrt(((pcs-centers[labels])**2).sum(1));metrics.update(pca_explained_top6=float(vals[-6:].sum()/max(vals.sum(),1e-12)),clusters=len(np.unique(labels)))
        diagnostics['group_business_summary']={int(g):{'count':int((labels==g).sum()),'margin':float(base[labels==g].sum())} for g in np.unique(labels)}
        checks['cluster_membership_conserved']=int(sum((labels==g).sum() for g in np.unique(labels)))==len(ids)
    elif f in [1,6,11,16]:
        common=rng.normal(size=(384,1));idio=rng.normal(size=(384,len(ids)))
        correlated=.45*common+np.sqrt(1-.45**2)*idio
        if f==1:
            survival=np.clip((df.active_months.to_numpy()+1)/25,.2,.99)
            retention=rng.random((384,len(ids),12))<survival[None,:,None]
            alive=np.cumprod(retention,axis=2);monthly=np.maximum(0,base)/(p['end']-p['start'])*30
            values=(alive*monthly[None,:,None]/(1+p['discount'])**np.arange(1,13)).sum(2)*(1+correlated*.12)
        elif f==6:
            pd0=np.clip(.01+df.dpd.to_numpy()/200+df.overdue.to_numpy()/np.maximum(df.balance.to_numpy(),1)*.1,.01,.6)
            failures=sigmoid(np.log(pd0/(1-pd0))[None,:]+correlated*.7)
            values=-df.balance.to_numpy()[None,:]*(rng.random(failures.shape)<failures)*(.4+.1*rng.random(failures.shape))
        else:
            std=np.sqrt(np.maximum(df.demand_variance.to_numpy(),0))
            demand=np.maximum(0,df.demand.to_numpy()[None,:]*df.lead_days.to_numpy()[None,:]+correlated*std[None,:]*np.sqrt(df.lead_days.to_numpy())[None,:])
            if f==11:
                need=np.maximum(0,np.quantile(demand,p['service'],axis=0)-df.on_hand.to_numpy());units=np.floor(need)
                cost=df.unit_cost.to_numpy();total=float(units@cost)
                if total>p['budget']:units=np.floor(units*p['budget']/total)
                allocation=units;benefit=np.mean(np.minimum(demand,df.on_hand.to_numpy()[None,:]+units),axis=0)*df.price.to_numpy()-units*cost
                values=benefit[None,:]+np.zeros_like(demand);checks['integer_nonnegative_budget']=bool(np.all(units>=0) and np.all(units==np.floor(units)) and units@cost<=p['budget']+1e-6)
                metrics['spend']=float(units@cost)
            else:
                outage=np.clip(df.downtime.to_numpy()[None,:]/max(1,p['end']-p['start'])/24+correlated*.03,0,.8)
                fulfilled=np.minimum(demand,df.capacity.to_numpy()[None,:]*(1-outage)*df.fill_rate.to_numpy()[None,:]/8)
                values=fulfilled*(df.price.to_numpy()-df.unit_cost.to_numpy())[None,:]-df.energy_cost.to_numpy()[None,:]/10
        mean=values.mean(0);q=np.quantile(values,.05,axis=0);tail=np.array([values[:,j][values[:,j]<=q[j]].mean() for j in range(len(ids))])
        if f!=11:allocation=mean;benefit=tail
        metrics.update(scenario_count=384,aggregate_p05=float(np.quantile(values.sum(1),.05)),aggregate_mean=float(values.sum(1).mean()),lower_tail_mean=float(tail.sum()))
        checks['tail_below_mean']=bool(np.all(tail<=mean+1e-7));diagnostics.update(mean=mean,lower_tail=tail)
    elif f==9:
        score=np.maximum(base,0)+df.earned.to_numpy()/12
        exposure=x[:,:8]
        risk_product=lambda w:exposure@(exposure.T@w)/8+.1*w
        r=score/max(float(score.max()),1);w=np.full(len(ids),1/len(ids));step=.5/(np.linalg.eigvalsh(exposure.T@exposure/8).max()+1.1)
        for _ in range(120):
            u=w+step*(r-p['risk']*risk_product(w));v=np.sort(u)[::-1];cs=np.cumsum(v)-1;rho=np.where(v>cs/(np.arange(len(v))+1))[0][-1];theta=cs[rho]/(rho+1);w=np.maximum(u-theta,0)
        allocation=w;benefit=w*score;metrics.update(objective=float(r@w-p['risk']/2*w@risk_product(w)),expected_margin=float(benefit.sum()))
        checks['simplex_weights']=bool(np.all(w>=0) and abs(w.sum()-1)<1e-8)
    else:
        # Full LP with budget, bounded per-entity participation and multiple independent resource constraints.
        if domain=='customer':
            cost=20+df.handling.to_numpy()*.08+df.arrears.to_numpy()*.025
            value=np.maximum(base,0)*.15+df.earned.to_numpy()*.1+df.outstanding.to_numpy()*.04
        else:
            cost=np.maximum(df.unit_cost.to_numpy(),.1)*(5+df.lead_days.to_numpy())
            value=np.maximum(df.margin.to_numpy(),0)*.01+df.demand.to_numpy()*(df.price.to_numpy()-df.unit_cost.to_numpy())
        if f in [7,12]:
            # Four service teams / receiving warehouses; each entity can split
            # resources across destinations with travel/handling penalties.
            route_distance=abs((group%4)[:,None]-np.arange(4)[None,:])
            route_cost=cost[:,None]*(1+.04*route_distance)
            route_value=value[:,None]*(1-.015*route_distance)
            constraints=[route_cost.ravel(),np.ones(len(ids)*4)]
            caps=[float(p['budget']),float(p['capacity'])]
            for station in range(4):
                row=np.zeros((len(ids),4));row[:,station]=1;constraints.append(row.ravel());caps.append(p['capacity']*.35)
            for entity in range(len(ids)):
                row=np.zeros((len(ids),4));row[entity,:]=1;constraints.append(row.ravel());caps.append(1)
            mat=np.vstack(constraints);rhs=np.asarray(caps)
            lp=linprog(-route_value.ravel(),A_ub=mat,b_ub=rhs,bounds=(0,1),method='highs')
            if not lp.success:raise AssertionError('routing LP infeasible')
            route=lp.x.reshape(len(ids),4);allocation=route.sum(1);benefit=(route*route_value).sum(1)
            metrics.update(spend=float((route*route_cost).sum()),objective=float(benefit.sum()),max_constraint_violation=float(np.max(mat@lp.x-rhs)))
            diagnostics.update(route_allocations=route,route_costs=route_cost,station_utilization=route.sum(0),station_capacity=p['capacity']*.35)
            checks.update(route_constraints=bool(np.all(mat@lp.x<=rhs+1e-6)),entity_allocation_bounds=bool(np.all(allocation<=1+1e-8)))
            checks['finite_complete_output']=bool(np.all(np.isfinite(allocation)) and np.all(np.isfinite(benefit)))
            return plain({'metrics':metrics,'diagnostics':diagnostics,'checks':checks,'decisions':np.column_stack([ids,allocation,benefit])})
        rows=[cost,np.ones(len(ids))];bounds=[float(p['budget']),float(p['capacity'])]
        if f in [14,19]:
            energy=df.energy_cost.to_numpy()/np.maximum(df.output.to_numpy(),1);carbon=df.carbon.to_numpy()/np.maximum(df.output.to_numpy(),1)
            rows.extend([energy,carbon]);bounds.extend([p['capacity']*np.quantile(energy,.7),p['capacity']*np.quantile(carbon,.7)])
        if f in [5,17]:
            for g in np.unique(group):rows.append(-(group==g).astype(float));bounds.append(-.25)
        matrix=np.vstack(rows);rhs=np.array(bounds)
        lp=linprog(-value,A_ub=matrix,b_ub=rhs,bounds=[(0,1)]*len(ids),method='highs')
        if not lp.success:raise AssertionError('decision LP infeasible: '+lp.message)
        allocation=lp.x;benefit=allocation*value;metrics.update(spend=float(allocation@cost),objective=float(benefit.sum()),max_constraint_violation=float(np.max(matrix@allocation-rhs)))
        diagnostics.update(resource_matrix=matrix,resource_caps=rhs,resource_utilization=matrix@allocation)
        checks.update(lp_resource_constraints=bool(np.all(matrix@allocation<=rhs+1e-6)),allocation_bounds=bool(np.all((allocation>=-1e-8)&(allocation<=1+1e-8))))
    checks['finite_complete_output']=bool(np.all(np.isfinite(allocation)) and np.all(np.isfinite(benefit)))
    return plain({'metrics':metrics,'diagnostics':diagnostics,'checks':checks,'decisions':np.column_stack([ids,allocation,benefit])})
