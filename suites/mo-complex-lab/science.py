"""Client computations, not claims that MO executes PCA or model fitting."""
import numpy as np

def compute(name,rows,i):
 a=np.asarray([[np.nan if v is None else float(v) for v in r] for r in rows],dtype=float)
 if not len(a):return [None]
 raw=a[:,2:9].copy(); missing=np.isnan(raw)
 med=np.nanmedian(raw,axis=0); med=np.nan_to_num(med)
 raw=np.where(missing,med,raw)
 X=(raw-raw.mean(0))/np.maximum(raw.std(0),1e-10)
 y=a[:,9]; y=(y-y.mean())/max(y.std(),1e-10)
 n,p=X.shape; Z=np.c_[np.ones(n),X]; reg=.01+(i%13)*.015
 cov=X.T@X/max(n-1,1)
 if name=='covariance_eigenvalues':return np.linalg.eigvalsh(cov)
 if name=='correlation_matrix':return (X.T@X/n).ravel()
 if name=='pca_explained_variance':
  e=np.linalg.eigvalsh(cov)[::-1];return e/max(e.sum(),1e-10)
 if name=='svd_spectrum':return np.linalg.svd(X,compute_uv=False)
 if name=='truncated_svd_error':
  u,s,v=np.linalg.svd(X,full_matrices=False); k=2+i%3; d=X-(u[:,:k]*s[:k])@v[:k];return [np.mean(d*d),np.max(np.abs(d))]
 if name=='qr_orthogonality':
  q,r=np.linalg.qr(Z);return [np.linalg.norm(q.T@q-np.eye(q.shape[1])),np.linalg.norm(q@r-Z)]
 if name=='ols_coefficients':return np.linalg.lstsq(Z,y,rcond=1e-10)[0]
 if name=='ridge_coefficients':return np.linalg.solve(Z.T@Z+reg*np.eye(p+1),Z.T@y)
 if name=='weighted_least_squares':
  w=1/(1+np.abs(y));return np.linalg.lstsq(Z*np.sqrt(w[:,None]),y*np.sqrt(w),rcond=1e-10)[0]
 if name=='huber_irls':
  b=np.zeros(p+1)
  for _ in range(12):
   residual=y-Z@b;w=np.minimum(1,1.345/np.maximum(np.abs(residual),1e-10)); b=np.linalg.solve(Z.T@(Z*w[:,None])+reg*np.eye(p+1),Z.T@(w*y))
  return b
 if name=='logistic_irls':
  target=(a[:,1]==1).astype(float); b=np.zeros(p+1)
  for _ in range(12):
   pr=1/(1+np.exp(-np.clip(Z@b,-30,30))); w=np.maximum(pr*(1-pr),1e-6)
   b+=np.linalg.solve(Z.T@(Z*w[:,None])+reg*np.eye(p+1),Z.T@(target-pr)-reg*b)
  return b
 if name=='kmeans_centroids':
  k=3; centers=X[np.linspace(0,n-1,k,dtype=int)].copy()
  for _ in range(15):
   labels=((X[:,None]-centers)**2).sum(2).argmin(1)
   centers=np.array([X[labels==j].mean(0) if np.any(labels==j) else centers[j] for j in range(k)])
  return centers.ravel()
 if name=='pairwise_cosine_distribution':
  norms=np.maximum(np.linalg.norm(X,axis=1),1e-10);sim=(X/norms[:,None])@(X/norms[:,None]).T;v=sim[np.triu_indices(n,1)];return np.quantile(v,[0,.1,.5,.9,1])
 if name=='mahalanobis_distance':
  inv=np.linalg.inv(cov+reg*np.eye(p));d=np.einsum('ij,jk,ik->i',X,inv,X);return np.quantile(d,[0,.25,.5,.75,1])
 if name=='fft_activity_power':return (np.abs(np.fft.rfft(X[:,5]))**2)[:16]
 if name=='convolution_activity':return np.convolve(X[:,5],np.ones(7)/7,mode='valid')[:16]
 if name=='bootstrap_mean_interval':
  rng=np.random.default_rng(20261011+i);v=raw[:,1];means=v[rng.integers(0,n,(128,n))].mean(1);return np.quantile(means,[.025,.5,.975])
 if name=='quantile_scaling':return np.quantile(raw,[.05,.25,.5,.75,.95],axis=0).ravel()
 if name=='gaussian_kernel_mmd':
  k=np.exp(-((X[:,None]-X[None,:])**2).sum(2)/(2+reg)); g=a[:,1]==0;h=~g
  return [k[np.ix_(g,g)].mean()+k[np.ix_(h,h)].mean()-2*k[np.ix_(g,h)].mean()]
 if name=='feature_missingness_imputation':return np.r_[missing.sum(0),med,raw.mean(0),raw.std(0)]
 raise ValueError(name)
