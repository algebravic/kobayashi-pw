A Fourier Approach to vertex separation
=======================================

Let \(G\) be an undirected simple connected graph, and \(n = \#V(G)\).
If \(v \in V(G)\) define \(N(v) = \{w \in V(G): (v,w) \in E(G)\}\).
For every one-to-one map \(sigma: V(G) \rightarrow \{1,\dots,n\}\) we
can define the **restricted neighborhood**
\(N(\sigma, v) = \{ w \in N(v): \sigma(w) \le \sigma(v)\}\)
**separation**
\[ S(\sigma, G) = \max_v \#N(\sigma, v).
\]
The **path width** of \(G\) is \(\min_\sigma S(\sigma, G)\).

David Coudert gave a mixed integer programming (MIP) model to find the
path width as follows:

There are 0/1 variables: \(x[v,t]\) for \(v \in V(G), t \in
\{1,\dots,n\}\), where \(x[v,t] = 1\) if and only if \(sigma(v) \le
t\).

\(y[i,u] = 1\) if and only if \(u \in N(\sigma, \sigma^{-1}(i))\)

Minimize \(p\) subject to
\[\tau(u,v,i) \le y[i,j], \forall v \in V(G), \forall v \in N(u),
\forall i \in [n]\]
\[\sum_{u \in V(G)} y[i,u] \le p, \forall i \in [n].
\]
Here \(\tau(u,v,i) = x[i,v] - x[i,u]\),
and \(x[i,u] = 1\) if and only if \(\sigma(u) \le i\).
We have
\[x[i,u] \le x[i+1,u], \forall u \in V(G), \forall i \in [n-1]\]
\[\sum_{u \in V(G)} x[i,j] = i, \forall i \in [n]\]

My idea is the \(S(\sigma, G)\) is a function of the permutation
\(sigma\) so we can expand it into a non-commutative Fourier series:

\[S(\sigma, G) = \sum_{\rho} \Tr(\rho(\sigma)^T A_\rho)\]
for some matrices \(A_\rho\), where the sum is over all the
irreducible representations of \(S_n\).
