#!/usr/bin/env python
# Muyuan Chen 2018-04
from EMAN2 import *
import numpy as np
import queue
import threading
from EMAN2jsondb import JSTask
from EMAN2PAR import EMTaskCustomer
from scipy.optimize import minimize
import gc
#from memory_profiler import profile

def main():
	
	usage=" "
	parser = EMArgumentParser(usage=usage,version=EMANVERSION)
	
	parser.add_argument("--ptclin", type=str,help="particle input", default=None)
	parser.add_argument("--ptclout", type=str,help="particle output", default=None)
	parser.add_argument("--ref", type=str,help="reference input", default=None)
	parser.add_argument("--keep", type=float,help="propotion of tilts to keep. default is 0.8", default=0.8)
	parser.add_argument("--parallel", type=str,help="Thread/mpi parallelism to use. Default is thread:12", default="thread:12")

	parser.add_argument("--debug", action="store_true", default=False ,help="Turn on debug mode. This will only process a small subset of the data")
	parser.add_argument("--maxshift", type=int,help="maximum shift allowed", default=8)
	parser.add_argument("--localrefine", action="store_true", default=False ,help="local refinement")
	parser.add_argument("--ctfweight", action="store_true", default=False ,help="weight by ctf")
	parser.add_argument("--maxres", type=float,default=-1, help="max resolution for cmp")
	#parser.add_argument("--minres", type=float,default=-1, help="min resolution for cmp")
	parser.add_argument("--sym", type=str,help="symmetry. ", default="c1")
	parser.add_argument("--ppid", type=int,help="ppid...", default=-1)
	parser.add_argument("--nkeep", type=int,help="", default=1)
	parser.add_argument("--verbose","-v", type=int,help="Verbose", default=0)

	(options, args) = parser.parse_args()
	logid=E2init(sys.argv)

	#gc.set_debug(gc.DEBUG_LEAK)
	lstname=options.ptclin
	threedname=options.ref
	lname=options.ptclout

	
	lst=LSXFile(lstname, True)
	m=EMData(threedname)
	bxsz=m["nx"]
	apix=m["apix_x"]
	
	options.shrink=1
	pinfo=[]
	nptcl=lst.n
	
	print("Initializing parallelism...")
	etc=EMTaskCustomer(options.parallel, module="e2spa_align.SpaAlignTask")	
	num_cpus = etc.cpu_est()
	
	print("{} particles".format(nptcl))
	print("{} total CPUs available".format(num_cpus))
	if options.debug: 
		nptcl=min(4*num_cpus, nptcl)
		print("Debugging mode. running on one thread with 8 particles")
		
	for i in range(nptcl):
		pinfo.append(lst.read(i))
	lst=None
	
	nbatch=min(nptcl//4, num_cpus)
	
	infos=[[] for i in range(nbatch)]
	for i,info in enumerate(pinfo):
		infos[i%nbatch].append([i, info])
		
	print("{} jobs, each with {:.1f} particles".format(len(infos), np.mean([len(i) for i in infos])))
	
	tids=[]
	for info in infos:
		task = SpaAlignTask(info, threedname, options)
			
		if options.debug:
			task.execute(print)
			return
		tid=etc.send_task(task)
		tids.append(tid)
	
	while 1:
		st_vals = etc.check_task(tids)
		if -100 in st_vals:
			print("Error occurs in parallelism. Exit")
			return
		E2progress(logid, np.mean(st_vals)/100.)
		
		if np.min(st_vals) == 100: break
		time.sleep(5)
	
	dics=[0]*nptcl
	for i in tids:
		ret=etc.get_results(i)[1]
		for r in ret:
			ii=r.pop("idx")
			dics[ii]=r
	
	del etc
	
	
	allscr=[d["score"] for d in dics]
	maxl=np.max([len(s) for s in allscr])
	maxv=np.max(np.concatenate(allscr))
	for s in allscr:
		s.extend([maxv]*(maxl-len(s)))
	allscr=np.array(allscr)
	
	
	try: os.remove(lname)
	except: pass
	lout=LSXFile(lname, False)
	for i, dc in enumerate(dics):
		lc=""
		for j,xf in enumerate(dc["xform.align3d"]):
			d=xf.get_params("eman")
			d["score"]=float(allscr[i,j])
			lc=lc+str(d)+';'
			
		l=pinfo[i]
		lout.write(-1, l[0], l[1], lc[:-1])

	lout=None
	E2end(logid)


def run(cmd):
	print(cmd)
	launch_childprocess(cmd)
	

class SpaAlignTask(JSTask):
	
	
	def __init__(self, info, ref, options):
		
		data={"info":info, "ref": ref}
		JSTask.__init__(self,"SptNewTltRefine",data,{},"")
		self.options=options
	
	#@profile
	def execute(self, callback):
		
		def test_rot(x, returnxf=False):
			fullxf=False
			if isinstance(x, Transform):
				xf=x
				
			else:
				if len(x)<4:
					xf=Transform({"type":"eman", "alt":x[0], "az":x[1], "phi":x[2]})
				else:
					xf=Transform({"type":"eman", "alt":x[0], "az":x[1], "phi":x[2],"tx":x[3], "ty":x[4]})
					fullxf=True			   
			
			pj=refsmall.project('gauss_fft',{"transform":xf, "returnfft":1})
			
			x0=ss//8; x1=int(ss*.4)
			ccf=imgsmall.calc_ccf(pj)
			pos=ccf.calc_max_location_wrap(mxsft, mxsft, 0)
			xf.set_trans(pos)
			#pj.translate(xf.get_trans())
			pj.process_inplace("xform", {"tx":pos[0], "ty":pos[1]})
		
			fsc=imgsmall.calc_fourier_shell_correlation(pj)
			fsc=np.array(fsc).reshape((3,-1))[:, x0:x1]
			wt=fsc[2]
			if ctfwt:
				wt*=ctfcv[x0:x1]
			
			scr=-np.sum(fsc[1]*wt)/np.sum(wt)
			del pj,ccf
			#scr=1
			if returnxf:
				return scr, xf
			else:
				return scr
		
		
		options=self.options
		data=self.data
		callback(0)
		rets=[]
		

		ref=EMData(data["ref"],0)
		ny0=ny=ref["ny"]
		
		if options.maxres>0:
			maxrescut=ceil(ny*ref["apix_x"]/options.maxres)
			maxy=good_size(maxrescut*3)
			maxy=int(min(maxy, ny))
		else:
			maxy=ny
			maxrescut=1e5
		
		ref.do_fft_inplace()
		ref.process_inplace("xform.phaseorigin.tocenter")
		ref.process_inplace("xform.fourierorigin.tocenter")
		ssrg=2**np.arange(4,12, dtype=int)
		ssrg[:2]=ssrg[:2]*3/2
		ssrg=ssrg.tolist()
		xfsit0=[]
		
		for infoi, infos in enumerate(data["info"]):
			time0=time.time()
			ii=infos[0]
			info=infos[1]
			
			img=EMData(info[1],info[0])
			if img["ny"]!=ny: # box size mismatch. simply clip the box
				by=img["ny"]
				img.clip_inplace(Region((by-ny)/2, (by-ny)/2, ny,ny))
				
			img.process_inplace("mask.soft",{"outer_radius":-10,"width":10})
			img.do_fft_inplace()
			img.process_inplace("xform.phaseorigin.tocenter")
			img.process_inplace("xform.fourierorigin.tocenter")
			img.process_inplace("filter.highpass.gauss",{"cutoff_pixels":4})
			path=[]
			
			npos=32
			istart=0
			initxfs=[]
				
			if isinstance(info[-1], str):
				for xfs in info[-1].split(';'):
					initxf=eval(xfs)
					if "score" in initxf:
						initxf.pop('score')
					initxfs.append(Transform(initxf))
					
			if options.localrefine:	
				newxfs=[]
				istart=1
				npos=npos//2
				for ixf in initxfs:
					ix=ixf.get_params("eman")
					for i in range(npos):
						d={"type":"eman","tx":ix["tx"], "ty":ix["ty"]}
						for ky in ["alt", "az", "phi"]:
							d[ky]=ix[ky]+np.random.randn()*5./np.pi*2
						newxfs.append(Transform(d))
				
			if img.has_attr("ctf") and options.ctfweight:
				ctf=img["ctf"]
				ds=1./(ny*ref["apix_x"])
				ctf.bfactor=10
				ctfcv=abs(np.array(ctf.compute_1d(ny,ds,Ctf.CtfType.CTF_AMP)))
				ci=np.where(np.diff(ctfcv)<0)[0][0]
				ctfcv[:ci]=ctfcv[ci]
				ctfwt=True
			else:
				ctfwt=False
				
			for si in range(istart, len(ssrg)):
				ss=ssrg[si]
				if ss>=maxy: 
					ss=maxy
					
				refsmall=ref.get_clip(Region(0,(ny-ss)//2, (ny-ss)//2, ss+2, ss, ss))
				imgsmall=img.get_clip(Region(0,(ny-ss)//2, ss+2, ss))
				imgsmall.process_inplace("xform.fourierorigin.tocenter")
					
				mxsft=ss//8
				astep=89.999/floor((np.pi/(3*np.arctan(2./ss))))*2
				sym=Symmetries.get(options.sym)
				score=[]
					
				if si==0:
					if len(xfsit0)==0:
						xfsit0=sym.gen_orientations("saff",{"delta":astep,"phitoo":astep,"inc_mirror":1})
					newxfs=[]
					for xf in xfsit0:
						scr, x=test_rot(xf, True)
						score.append(scr)
						newxfs.append(x)
				else:
					xfs=newxfs
					if len(initxfs)>0:	
						xfs.append(initxfs[0])
					newxfs=[]
					simplex=np.vstack([[0,0,0], np.eye(3)*astep])
					for xf0 in xfs:
						x=xf0.get_params("eman")
						x0=[x["alt"], x["az"], x["phi"]]
						res=minimize(test_rot, x0, method='Nelder-Mead', options={'ftol': 1e-2, 'disp': False, "maxiter":50, "initial_simplex":simplex+x0})
						scr, x=test_rot(res.x, True)
						score.append(scr)
						newxfs.append(x)
						
				xfs=newxfs

				newxfs=[]
				newscore=[]
				idx=np.argsort(score)
				for i in idx:
					dt=[(x.inverse()*xfs[i]).get_params("spin")["omega"] for x in newxfs]
					if len(dt)==0 or np.min(dt)>astep*4:
						newxfs.append(xfs[i])
						newscore.append(score[i])
					if len(newxfs)>=npos:
						break
					
				for xf in newxfs:
					xf.set_trans(xf.get_trans()*ny/ss)
					
				if options.verbose>1:
					print("size: {}, xfs: {}".format(ss, len(newxfs)))
					for x in newxfs:
						xf=x.get_params("eman")
						print("\t{:.1f} {:.1f} {:.1f} {:.1f} {:.1f}".format(xf["alt"], xf["az"], xf["phi"], xf['tx'], xf['ty']))
				
				npos=max(1, npos//2)
				lastastep=astep
				#path.append(newxfs)
				del refsmall,imgsmall,xfs
				if ss>=maxy:
					break
				
			#r={"idx":ii, "xform.align3d":newxfs[0], "score":np.min(score)}
			r={"idx":ii, "xform.align3d":newxfs[:options.nkeep], "score":newscore[:options.nkeep], "path":path}
			del img
			if not options.debug:
				callback(100*float(infoi/len(self.data["info"])))
			rets.append(r)
			
			#print(gc.garbage)
			if options.debug:
				print("time : {:.1f}, best score {:.2f}".format(time.time()-time0, newscore[0]))
				#print(sys.getsizeof(rets))
				#objects=[]
				#loc=locals().items()
				#for name,obj in loc:
					#objects.append([name,sys.getsizeof(obj)])
				#mem=sorted(objects,key=lambda x: x[1],reverse=True)
				#for m in mem[:10]:
					#print("\t",m[0], m[1])
			
		return rets


	
if __name__ == '__main__':
	main()