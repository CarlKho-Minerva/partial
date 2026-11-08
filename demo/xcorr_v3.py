import sys, wave, numpy as np
def load(p):
    with wave.open(p) as w: sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float64)
    return x,sr
s=sys.argv[1]
a,sr=load(f"{s}-screen.wav"); b,_=load(f"{s}-camera.wav")
a=np.diff(a); b=np.diff(b)
win=int(6*sr); hop=int(5*sr); L=int(2.5*sr)
rows=[]
for st in range(L, min(len(a),len(b))-win-L, hop):
    aa=a[st:st+win]; aa=(aa-aa.mean())/(aa.std()+1e-9)
    bb=b[st-L:st+win+L]; bb=(bb-bb.mean())/(bb.std()+1e-9)
    cc=np.correlate(bb,aa,mode="valid"); j=int(np.argmax(cc)); z=(cc[j]-cc.mean())/(cc.std()+1e-9)
    rows.append((st/sr,(j-L)/sr*1000,z))
for t,lag,z in rows: print(f"t={t:6.1f}s lag={lag:+8.1f} ms z={z:5.1f}")
