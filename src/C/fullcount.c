/* Count pw-feasible prefix sets (all subsets, no relevant-set pruning) level by level,
   forward only, then backward co-reachability; report totals.  Undirected, n<=64. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint64_t u64;
static int n, k; static u64 nin[64], full;
typedef struct { u64 *key; u64 *nb; size_t cap, len; } Tab;
static inline size_t H(u64 x){x^=x>>33;x*=0xff51afd7ed558ccdULL;x^=x>>33;return x;}
static void tinit(Tab*t,size_t cap){t->cap=cap;t->len=0;t->key=calloc(cap,8);t->nb=malloc(cap*8);}
static void tins(Tab*t,u64 S,u64 nb);
static void grow(Tab*t){Tab o=*t;tinit(t,o.cap*2);for(size_t i=0;i<o.cap;i++)if(o.key[i])tins(t,o.key[i]-1,o.nb[i]);free(o.key);free(o.nb);}
static void tins(Tab*t,u64 S,u64 nb){if(2*(t->len+1)>t->cap)grow(t);size_t i=H(S+1)&(t->cap-1);
  while(t->key[i]){if(t->key[i]==S+1)return;i=(i+1)&(t->cap-1);}t->key[i]=S+1;t->nb[i]=nb;t->len++;}
static int thas(Tab*t,u64 S){size_t i=H(S+1)&(t->cap-1);while(t->key[i]){if(t->key[i]==S+1)return 1;i=(i+1)&(t->cap-1);}return 0;}
int main(int argc,char**argv){
  k=atoi(argv[2]); FILE*f=fopen(argv[1],"r"); char line[256]; int maxl=0;
  while(fgets(line,256,f)){int u,v,c=sscanf(line,"%d %d",&u,&v); if(c>=1&&u>maxl)maxl=u; if(c==2){if(v>maxl)maxl=v; u--;v--; nin[u]|=1ULL<<v; nin[v]|=1ULL<<u;}}
  n=maxl; full=(n==64)?~0ULL:(1ULL<<n)-1;   /* labels 1..n -> bits 0..n-1 */
  Tab*L=calloc(n+1,sizeof(Tab)); tinit(&L[0],16); tins(&L[0],0,0);
  size_t tot=1, peak=1;
  for(int i=0;i<n;i++){ tinit(&L[i+1],1024);
    for(size_t j=0;j<L[i].cap;j++) if(L[i].key[j]){ u64 S=L[i].key[j]-1, nb=L[i].nb[j];
      for(u64 m=full&~S;m;m&=m-1){int x=__builtin_ctzll(m); u64 T=S|(1ULL<<x), nbT=nb|nin[x];
        if(__builtin_popcountll(nbT&~T)<=k) tins(&L[i+1],T,nbT);}}
    tot+=L[i+1].len; if(L[i+1].len>peak)peak=L[i+1].len; }
  /* backward: mark co-reachable by deleting nb (reuse nb as flag) */
  size_t good=0;
  for(int i=n;i>=0;i--) for(size_t j=0;j<L[i].cap;j++) if(L[i].key[j]){ u64 S=L[i].key[j]-1; int ok=(S==full);
      if(!ok) for(u64 m=full&~S;m&&!ok;m&=m-1){u64 T=S|(m&-m); size_t q=H(T+1)&(L[i+1].cap-1);
          while(L[i+1].key[q]){ if(L[i+1].key[q]==T+1){ ok = L[i+1].nb[q]!=~0ULL? 0:1; break;} q=(q+1)&(L[i+1].cap-1);} }
      /* mark good with nb = ~0 */
      if(ok){L[i].nb[j]=~0ULL; good++;} else if(L[i].nb[j]==~0ULL) L[i].nb[j]=0; }
  printf("n=%d k=%d feasible=%zu peak_layer=%zu on_opt_path=%zu\n",n,k,tot,peak,good);
  return 0;
}
