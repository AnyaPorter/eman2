#!/usr/bin/env python
# Muyuan Chen 2023-09
from EMAN2 import *
import numpy as np
from Bio.PDB import *
import protein_constant as e2pc
import scipy.sparse as scipysparse
from sklearn.cluster import KMeans
import scipy.spatial.distance as scipydist
from scipy.spatial import KDTree

floattype=np.float32
if "CUDA_VISIBLE_DEVICES" not in os.environ:
	# so we can decide which gpu to use with environmental variable
	os.environ["CUDA_VISIBLE_DEVICES"]='0' 
	
os.environ["TF_FORCE_GPU_ALLOW_GROWTH"]='true' 
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2' #### reduce log output
import tensorflow as tf


#### we will import some functions from e2gmm_refine later
emdir=e2getinstalldir()
sys.path.insert(0,os.path.join(emdir,'bin'))
from e2gmm_refine_new import set_indices_boxsz, load_particles, pts2img, calc_frc, get_clip, make_mask_gmm
from e2gmm_model_refine import calc_clashid, calc_bond, calc_angle, compile_chi_matrix, get_rotamer_angle, rotate_sidechain, get_info, calc_dihedral_tf, eval_rama, get_rama_types, compile_hydrogen, add_h, get_h_rotation_axis, optimize_h
from e2gmm_model_fit import build_decoder_anchor

#### slightly different version than the one in e2gmm_model_refine
def save_model_pdb(pout, options, fname, thetas=[]):

	if np.max(pout[:,:,:3])>1:
		# print("already in Angstron")
		atom_pos=pout
	else:
		atom_pos=(pout[:,:,:3]*[1,-1,-1]+0.5)*options.apix*options.maxboxsz
        
	# atom_pos=(pout[:,:,:3]*[1,-1,-1]+0.5)*options.apix*options.maxboxsz
	atom_pos=atom_pos[0].numpy()

	if options.modelpdb.endswith(".cif"):
		pdbpar = MMCIFParser( QUIET = True) 
	else:
		pdbpar = PDBParser( QUIET = True) 
	pdbh = pdbpar.get_structure("model",options.modelpdb)

	residue=list(pdbh.get_residues())
	for r in residue:
		d=list(r.child_dict)
		for a in d:
			if a[0]=='H':
				r.detach_child(a)

	atoms0=list(pdbh.get_atoms())
	for i,a in enumerate(atoms0):
		a.set_coord(atom_pos[i])

	if len(atom_pos)>len(atoms0):
		print("adding H")
		res1=list(pdbh.get_residues())
		h=atom_pos[options.npt_noh:]
		for ii,hl in enumerate(options.h_info[0]):
			a=Atom.Atom(hl[0], h[ii], 50, 1, ' ', hl[0], atoms0[-1].serial_number+ii+1, element='H')
			i=hl[2]
			a.set_parent(res1[i])
			res1[i].add(a)
			
	if options.modelpdb.endswith(".cif"):
		io=MMCIFIO()
		fname+=".cif"
	else:
		io=PDBIO()
		fname+=".pdb"

	io.set_structure(pdbh)
	io.save(fname)
	print(f"model saved to {fname}")

def find_clash(atom_pos, options, relu=True, clashid=[], subset=[], clashomask=[], vdw=[]):

	if len(clashid)==0:
		pc=tf.gather(atom_pos, options.clashid, axis=1)
		pc=pc-atom_pos[:,:,None, :]
	else:
		pc=tf.gather(atom_pos, clashid, axis=1)
		if len(subset)==0:
			ac=atom_pos
		else:
			ac=tf.gather(atom_pos, subset, axis=1)
		pc=pc-ac[:,:,None, :]
		
	pc=tf.math.sqrt(tf.reduce_sum(pc*pc, axis=3))
	
	if len(vdw)==0:
		vdw=options.vdw_radius
	if len(clashomask)==0:
		clashomask=options.clash_omask
		
	clash=vdw-pc-options.vdroverlap
	clash=clash-clashomask
		
	if relu:
		clash=tf.maximum(0,clash)
	return clash

def build_decoder_full(p0, options):
	kinit=tf.keras.initializers.RandomNormal(0,1e-7)

	layers=[
		tf.keras.layers.Dense(128, activation="relu"),
		tf.keras.layers.Dense(256, activation="relu"),
		# tf.keras.layers.Dropout(.1),
		tf.keras.layers.Dense(512, activation="relu"),
		tf.keras.layers.Dropout(.1),
		tf.keras.layers.Dense(np.prod(p0.shape), activation="linear", kernel_initializer=kinit),
		tf.keras.layers.Reshape(p0.shape),
		]

	x0=tf.keras.Input(shape=(options.nmid))

	y0=x0
	for l in layers:
		y0=l(y0)

	model=tf.keras.Model(x0, y0)

	return model
	
	
def calc_clashid(pts, options,  pad=40, nnb=-1, subset=[]):
	tree=KDTree(pts)
	vdwr=options.vdwr_h 
	if len(subset)>0:
		pp=pts[subset]
	else:
		pp=pts
		
	if nnb<0:
		nnb=options.clash_nb
		
	d,pnb=tree.query(pp, pad+nnb)

	clashid=[]
	# print(d.shape, pnb.shape)
	for i, nb0 in enumerate(pnb):
		if len(subset)>0:
			i=subset[i]
		
		nb=nb0[~np.isin(nb0, options.connect_all[i])].astype(int)
		d=np.linalg.norm(pts[i]-pts[nb], axis=1)
		d0=vdwr[nb]+vdwr[i]
		vid=np.argsort(d-d0)[:nnb]
		clashid.append(np.array(nb)[vid])

	clashid=np.array(clashid)
	return clashid


def main():
	
	usage="""
	GMM based model flexible fitting and refinement to a series of conformations.
	
	"""
	parser = EMArgumentParser(usage=usage,version=EMANVERSION)
	parser.add_argument("--path", type=str,help="folder generated by e2gmm_compile_model", default=None)
	parser.add_argument("--niter", type=str, help="number of iteration for loose and tight constraints, then fulll model refinement. The last number is 0/1 and only controls whether the full refinement is performed. default is 10,20,0",default="10,20,0")
	parser.add_argument("--modelpdb", type=str,help="neutral state pdb model input.", default=None)
	parser.add_argument("--modeltxt", type=str,help="neutral state model input in txt. e2gmm_model_fit.py should generate this with the --writetxt option", default=None)
	parser.add_argument("--maps", type=str,help="stack of map file for model fitting.", default=None)
	parser.add_argument("--projections", type=str,help="projections of the map stack. This will be generated if the specified file does not exist. Otherwise the program will read the existing file and ignore --map. Default is <path>/projections_stack.hdf .", default=None)
	parser.add_argument("--mask", type=str,help="mask for the focused region of heterogeneity analysis.", default=None)
	parser.add_argument("--resolution", type=float,help="target resolution.", default=8.)
	# parser.add_argument("--learnrate", type=float,help="learning rate.", default=1e-5)
	parser.add_argument("--npatch", type=int,help="number of patch for large scale flexible fitting. default is 64", default=64)
	parser.add_argument("--ndim", type=int,help="number of dimension of the input movement. Currently only support: 1 -> linear trajectory, 2 -> circular trajectory", default=2)
	parser.add_argument("--batchsz", type=int,help="batch size. default is 16", default=16)
	parser.add_argument("--load", action="store_true", default=False ,help="load existing networks")
	parser.add_argument("--evalmodel", type=int, help="Skip training and only generate models. Specify the number of frame here.",default=-1)
	parser.add_argument("--ppid", type=int, help="Set the PID of the parent process, used for cross platform PPID",default=-1)

	(options, args) = parser.parse_args()
	logid=E2init(sys.argv,options.ppid)
	
	path=options.path
	niter=[int(i) for i in options.niter.split(',')]
	if options.evalmodel>0: 
		niter=[0,0,0]
		options.load=True
	if len(niter)!=3:
		print("require 3 numbers for --niter")
		exit()
		
	if (niter[0]==0 or (niter[1]==0 and niter[2]>0)) and options.load==False:
		print("need --load when there are 0 in --niter")
		exit()
	print(niter)
		
	if options.projections==None:
		pname0=f"{path}/projections_stack.hdf"
	else: 
		pname0=options.projections
		
	
	if os.path.isfile(pname0):
		print(f"{pname0} already exist. reading projections from file...")
		
	else:
		tname0=options.maps
		n=EMUtil.get_image_count(tname0)
		for i in range(n):
			tname=f"{path}tmp3d.hdf"
			if os.path.isfile(tname): os.remove(tname)
			pname=f"{path}/tmp2d.hdf"
			if os.path.isfile(pname): os.remove(pname)
			e=EMData(tname0, i)
			e.write_image(tname)
			run(f"e2project3d.py {tname} --outfile {pname} --orientgen eman:delta=5 --parallel thread:32")
			
			n2=EMUtil.get_image_count(pname)
			for j in range(n2):
				a=EMData(pname, j)
				a.write_image(pname0, -1)
		
		if os.path.isfile(tname): os.remove(tname)
		if os.path.isfile(pname): os.remove(pname)
	
	
	if options.modelpdb.endswith(".cif"):
		pdbpar = MMCIFParser( QUIET = True) 
	else:
		pdbpar = PDBParser( QUIET = True) 
		
	pdb = pdbpar.get_structure("model",options.modelpdb)
	residue=list(pdb.get_residues())

	for r in residue:
		d=list(r.child_dict)
		for a in d:
			if a[0]=='H':
				r.detach_child(a)
				
	atoms=options.atoms=list(pdb.get_atoms())
	atom_pos=np.array([a.get_coord() for a in atoms])
	print(f"Input model: {options.modelpdb}")
	print(f"  {len(residue)} residues, {len(atoms)} atoms.")

	options.ptclsin=pname0

	##########################################
	##   load metadata first
	e=EMData(options.ptclsin, 0, True)
	raw_apix, raw_boxsz = e["apix_x"], e["ny"]
	maxboxsz=ceil(raw_boxsz*raw_apix/options.resolution*2)//2*2
	options.maxboxsz=maxboxsz
	options.trainmodel=False
	options.clip=-1
	options.apix=apix=raw_apix*raw_boxsz/maxboxsz
	
	#### only load particles when fitting model to maps
	if niter[0]==0 and niter[1]==0:
		print("Model refinement only, no particles needed")
		nptcl=8
	else:
		data_cpx, xfsnp = load_particles(options)
		print("Image size: ", data_cpx[0].shape)
		
		
		clipid=set_indices_boxsz(data_cpx[0].shape[1], apix, True)
		params=set_indices_boxsz(maxboxsz)
		dcpx=get_clip(data_cpx, params["sz"], clipid)
		nptcl=len(xfsnp)

	##########################################
	print("Initializing...")
	pts=np.loadtxt(options.modeltxt)
	
	#### here using Amp, Sigma from the txt model, but replace the xyz with the pdb model
	p=np.array([a.get_coord() for a in atoms])
	p=p/raw_boxsz/raw_apix-0.5
	p[:,1:]*=-1
	pts[:,:3]=p
	
	#### dealing with masking
	imsk=make_mask_gmm(options.mask, pts)
	
	##############
	resid0=[get_info(a, True) for a in atoms]
	resid, caidx=np.unique(resid0, return_inverse=True)
	capos=np.array([np.mean(pts[caidx==i], axis=0) for i in range(np.max(caidx)+1)])
	res_atom_dict={r:np.where(caidx==i)[0] for i,r in enumerate(resid)}
	print("Shape of CA model: ",capos.shape)
	
	#### force different chains to be in different classes
	## is this a good idea?
	cid=[r.split('_')[0] for r in resid0]
	rid=[r.split('_')[-1] for r in resid0]
	# print(rid)
	for i,r in enumerate(rid):
		if r in ["A","T","C","G","U","I","DA","DT","DC","DG","DU","DI"]:
			cid[i]="XNA"
	
	c,cid=np.unique(cid, return_inverse=True)
	print("{} chains".format(len(c)))
	# print(c)
	
	pcls=pts[:,:4].copy()
	pcls[:,3]=cid
	
	## anchor points for large scale movement
	afile=f"{path}/model_00_anchor.txt"
	if os.path.isfile(afile):
		print(f"Loading anchor points from {afile}")
		pcnt=np.loadtxt(afile)
	
	else:
		if options.mask==None:
			
			pn=options.npatch
			km=KMeans(pn,max_iter=30)
			km.fit(pcls)
			pcnt=km.cluster_centers_

			
		else:		
			## when there is a mask, sample more anchor points inside mask
			pn=32
			km=KMeans(pn,max_iter=30)
			km.fit(pcls[imsk<.1])
			pc0=km.cluster_centers_

			pn=options.npatch-pn
			km=KMeans(pn,max_iter=30)
			km.fit(pcls[imsk>.1])
			pc1=km.cluster_centers_

			pcnt=np.vstack([pc0,pc1])
			# print(pc0.shape, pc1.shape, pcnt.shape)
		
		np.savetxt(afile, pcnt)
		print(f"Anchor points saved to {afile}")
		
	d=scipydist.cdist(pcls, pcnt)
	klb=np.argmin(d, axis=1)
	options.learnrate=1e-5
	icls=np.zeros(len(pts), dtype=int)
	# options.batchsz=16
	for i in range(options.npatch):
		ii=np.where(klb==i)[0]
		ii=caidx[ii]
		# print(i, len(ii), np.sum(np.isin(caidx, ii)))
		icls[np.isin(caidx, ii)]=i
	
	# print(np.unique(icls, return_counts=True))
	
	##########################################
	## first model for large scale morphing
	options.nmid=4
	gen_model=build_decoder_anchor(pts[None,...], icls, options.nmid, meanzero=True)
	conf=tf.zeros((2, options.nmid,), dtype=floattype)+1.
	pout=gen_model(conf)
	wfile0=f"{path}/weights_morph.h5"
	wfile1=f"{path}/weights_ca.h5"
	wfile2=f"{path}/weights_full.h5"
	if options.load and os.path.isfile(wfile0):
		gen_model.load_weights(wfile0)
	
	
	#### latent space input. currently only linear or circular path
	n=EMUtil.get_image_count(options.maps)
		
	if options.ndim==1:
		a=np.arange(n)/(n-1)*2-1
		mid00=np.repeat(a[:,None], 4, axis=1)
		mid2=mid00.copy()
		print(mid2)
		
	if options.ndim==2:
		rr=1.0
		a=np.arange(n)/n*np.pi*2
		t=rr*np.vstack([np.cos(a), np.cos(a), np.sin(a), np.sin(a)]).T
		# print(np.round(t,3))
		mid00=t.copy()
		mid2=mid00[::2].copy()
	
	midii=np.arange(nptcl)//(nptcl/n)
	midpos=mid00[midii.astype(int)].astype(floattype)
	
	if niter[0]>0 or niter[1]>0:
		trainset=tf.data.Dataset.from_tensor_slices((dcpx[0], dcpx[1], xfsnp, midpos))
		trainset=trainset.shuffle(5000).batch(options.batchsz)
		
		options.minpx=4
		options.maxpx=maxboxsz//2
		nbatch=int(trainset.cardinality())
		
	##############
	## first train morphing model
	if niter[0]>0:
		print("Large scale model morphing...")
		opt=tf.keras.optimizers.Adam(learning_rate=options.learnrate) 
		wts=gen_model.trainable_variables
		
		for bxn in [4,3,2]:
			options.maxpx=maxboxsz//bxn
			##########################################
			etc=""
			print("  Max resolution {:.1f}".format(options.resolution*bxn/2))
			
			for itr in range(niter[0]):
				cost=[]
				costetc=[]
				for pjr,pji,xf,md in trainset:
					if xf.shape[0]==1: continue
					pj_cpx=(pjr,pji)
					with tf.GradientTape() as gt:

						conf=md
						conf+=0.02*tf.random.normal(conf.shape)
						pout=gen_model(conf, training=True)
						pout=pout*imsk[None,:,None]
						pout+=pts

						imgs_cpx=pts2img(pout, xf)
						fval=calc_frc(pj_cpx, imgs_cpx, params["rings"], minpx=options.minpx, maxpx=options.maxpx)
						loss=-tf.reduce_mean(fval)

					cost.append(loss)  

					assert np.isnan(loss.numpy())==False

					grad=gt.gradient(loss, wts)
					opt.apply_gradients(zip(grad, wts))	

					print("{}/{}\t{:.3f}{}         ".format(len(cost), nbatch, loss, etc), end='\r')

				print("iter {}, loss : {:.4f},  {} ".format(itr, np.mean(cost),etc))
		
		pout=gen_model(mid2, training=False)
		pout=pout*imsk[None,:,None]
		pout+=pts

		for i,pp in enumerate(pout):
			save_model_pdb(pp[None,:], options, f"{path}/fit01_flex0_{i:02d}")		
		
		if os.path.isfile(wfile0): os.remove(wfile0)
		gen_model.save_weights(wfile0)

	#### now build model for C-alpha movement
	gen_model_ca=build_decoder_anchor(pts[None,...], caidx, meanzero=True, freeamp=False)
	conf=tf.zeros((2,4), dtype=floattype)+1.
	d=gen_model_ca(conf)[0]
	
	if options.load and os.path.isfile(wfile1):
		gen_model_ca.load_weights(wfile1)
	
	pout=tf.constant(pts.copy()[None,:].astype(floattype))
	atom_pos=(pout[:,:,:3]*[1,-1,-1]+0.5)*options.apix*options.maxboxsz

	##########################################
	idx_rama=np.loadtxt(f"{path}/model_rama_angle.txt").astype(int)
	options.bonds=bonds=np.loadtxt(f"{path}/model_bond.txt").astype(floattype)
	options.angle=np.loadtxt(f"{path}/model_angle.txt").astype(floattype)
	options.vdwr_h=vdwr=np.loadtxt(f"{path}/model_vdwr.txt").astype(floattype)
	options.idx_dih_rama=np.loadtxt(f"{path}/model_rama_angle.txt").astype(int)
	options.idx_dih_plane=np.loadtxt(f"{path}/model_dih_plane.txt").astype(int)
	options.idx_dih_piptide=np.loadtxt(f"{path}/model_dih_piptide.txt").astype(int)
	options.idx_dih_chi=np.loadtxt(f"{path}/model_dih_chi.txt").astype(int)
	
	options.clash_nb=128
	options.vdroverlap=.5

	bd=bonds[:,:2].astype(int)
	npt=len(atoms)
	maxlen=3
	bonds_matrix=scipysparse.csr_matrix((np.ones(len(bd)), (bd[:,0], bd[:,1])), shape=(npt,npt))

	d = scipysparse.csgraph.dijkstra(bonds_matrix, directed=False, limit=maxlen)
	options.connect_all=[np.where(i<=maxlen)[0] for i in d]
	options.clashid=calc_clashid(atom_pos[0].numpy(), options, pad=60)
	options.vdw_radius=tf.gather(options.vdwr_h, options.clashid)+options.vdwr_h[:,None]
	options.clash_omask=np.zeros_like(options.clashid)

	clash=find_clash(atom_pos, options)

	#### TODO H-bonds for DNA/RNAs...

	if niter[1]>0:
		wts=gen_model_ca.trainable_variables	
		options.learnrate=1e-5
		opt=tf.keras.optimizers.Adam(learning_rate=options.learnrate) 
		weight_model=1e-6
		costall=[]
		print("C-alpha model refinement...")
		print("iter,   loss,   bond outlier,  angle outlier, clash_score,  number of clash")
		for itr in range(niter[1]):
			cost=[]
			costetc=[]
			for pjr,pji,xf,md in trainset:
				if xf.shape[0]==1: continue
				pj_cpx=(pjr,pji)
				with tf.GradientTape() as gt:

					conf=md
					# print(conf.shape)
					conf+=0.02*tf.random.normal(conf.shape)
					pout=gen_model(conf, training=True)
					pout=pout+gen_model_ca(conf, training=True)
					pout=pout*imsk[None,:,None]
					pout+=pts

					imgs_cpx=pts2img(pout, xf)
					fval=calc_frc(pj_cpx, imgs_cpx, params["rings"], minpx=options.minpx, maxpx=options.maxpx)
					loss=-tf.reduce_mean(fval)


					atom_pos=(pout[:,:,:3]*[1,-1,-1]+0.5)*options.apix*options.maxboxsz

					bond_len=calc_bond(atom_pos, bonds[:,:2].astype(int))
					bond_df=(bond_len-bonds[:,2])/bonds[:,3]
					bond_outlier=tf.maximum(abs(bond_df)-4, 0)
					bond_outlier=tf.reduce_mean(bond_outlier)*1000*20


					ang_val=calc_angle(atom_pos, options.angle[:,:3].astype(int))
					ang_df=(ang_val-options.angle[:,3])/options.angle[:,4]
					ang_outlier=tf.maximum(abs(ang_df)-4, 0)
					ang_outlier=tf.reduce_mean(ang_outlier)*1000*20

					clash=find_clash(atom_pos, options)

					nclash=np.sum(clash.numpy()>0)/conf.shape[0]//2
					clash_score=tf.reduce_sum(clash)/conf.shape[0]/2.

					lossetc=0.
					lossetc+=bond_outlier
					lossetc+=ang_outlier
					lossetc+=clash_score


					l=loss*1+lossetc*weight_model

				cost.append(loss)  
				costetc.append(lossetc)  

				assert np.isnan(l.numpy())==False

				grad=gt.gradient(l, wts)
				opt.apply_gradients(zip(grad, wts))
				etc=""
				etc+=f", {bond_outlier:.3f}, {ang_outlier:.3f}, {clash_score:.3f}, {nclash}"


				print("{}/{}\t{:.3f}{}         ".format(len(cost), nbatch, loss, etc), end='\r')

			print("iter {}, loss : {:.4f},  {} ".format(itr, np.mean(cost),etc))
			costall.append([np.mean(cost), np.mean(costetc)])
			
		pout=gen_model(mid2, training=False)
		pout=pout+gen_model_ca(mid2, training=False)
		pout=pout*imsk[None,:,None]
		pout+=pts

		for i,pp in enumerate(pout):
			save_model_pdb(pp[None,:], options, f"{path}/fit01_flex1_{i:02d}")
		
		if os.path.isfile(wfile1): os.remove(wfile1)
		gen_model_ca.save_weights(wfile1)
	
	##############
	#### make models with a relatively even spacing 
	if options.evalmodel>0:
		gen_model_full=build_decoder_full(pts, options)
		gen_model_full.load_weights(wfile2)
			
		n=options.evalmodel
		a=np.arange(n)/(n-1)
		
		for ie in range(7):
			if options.ndim==1:
				a=a*2-1
				conf=np.repeat(a[:,None], 4, axis=1)
			if options.ndim==2:
				a=a*np.pi*2
				conf=rr*np.vstack([np.cos(a), np.cos(a), np.sin(a), np.sin(a)]).T
				
			# print("########\n",a)
			pout=gen_model(conf, training=False)
			pout=pout+gen_model_ca(conf, training=False)
			pout=pout*imsk[None,:,None]
			pout=pout+gen_model_full(conf, training=False)    
			pout+=pts
			
			df=np.diff(pout[:,:,:3], axis=0)
			df=np.linalg.norm(df, axis=2)
			
			df=np.max(df, axis=1)
			# print(df)
			
			a=np.append(0,np.cumsum(np.diff(a)/df))
			a=a/a[-1]
		
		
		atom_pos=(pout[:,:,:3]*[1,-1,-1]+0.5)*options.apix*options.maxboxsz
		# atom_pos_h=add_h(atom_pos, options.h_info)
		
		for i,pp in enumerate(atom_pos):
			save_model_pdb(pp[None,:], options, f"{path}/fit01_flex3_{i:02d}")
		
			
	
	if niter[2]==0:
		E2end(logid)
		return
		
	
	#########################################	
	print("Compiling Ramachandran types...")
	options.dih_type=dih_type=get_rama_types(atoms, idx_rama)
	rt={"general":"General","gly":"GLY","protrans":"trans-PRO","procis":"cis-PRO","ile":"ILE/VAL","prepro":"pre-PRO"}
	for k in dih_type:
		print(f"  Ramachandran type {rt[k]:<10}:  {int(np.sum(dih_type[k]))} residues.")
		
	print("Compiling rotamers...")
	options.chi_idx, options.chi_mat=compile_chi_matrix(options.idx_dih_chi)

	##########################################
	options.thr_plane=np.sin(10*np.pi/180)
	options.thr_piptide=np.sin(30*np.pi/180)
	options.nstd_bond=4.5
	options.nstd_angle=4.5
	options.vdroverlap=0.35
	ramalevel=[0.0005,0.02]
	options.rama_thr0=1-ramalevel[1]*1.1
	options.rama_thr1=1-ramalevel[0]*2	


	print("Building full atom model...")
	gen_model_full=build_decoder_full(pts, options)
	wts=gen_model_full.trainable_variables
	cost=[]
	optimizer=tf.keras.optimizers.Adam(learning_rate=1e-5)
	
	conf=mid2
	pout=gen_model(conf, training=False)
	pout=pout+gen_model_ca(conf, training=False)
	pout=pout*imsk[None,:,None]
	pout=pout+gen_model_full(conf, training=False)    
	pout+=pts
	atom_pos=(pout[:,:,:3]*[1,-1,-1]+0.5)*options.apix*options.maxboxsz
	
	#### H atoms
	options.h_info=compile_hydrogen(pdb)
	h_label, h_ref, h_offset=options.h_info
	options.npt_noh=npt_noh=len(atoms)
	options.npt_h=npt_h=len(h_label)

	print(f"  {npt_noh} non-H atoms. Adding {npt_h} H")
	atom_pos_h=add_h(atom_pos, options.h_info)
	
	#### bonds between H and non-H
	hb=np.array([np.arange(npt_h)+npt_noh, h_ref[:,0], np.zeros(npt_h), np.zeros(npt_h)], dtype=floattype).T
	ah=atom_pos_h[0].numpy()
	d=np.linalg.norm(ah[hb[:,0].astype(int)]-ah[hb[:,1].astype(int)], axis=1)
	hb[:,2]=d
	hb[:,3]=0.02
	bonds_h=np.vstack([bonds, hb])
	
	#### vdw radius of H
	lbs=["{}_{}".format(h[1].resname,h[0]) for h in h_label]
	vdwh=np.array([e2pc.get_vdw_radius(i) for i in lbs])
	options.vdwr_h=np.append(vdwr, vdwh).astype(floattype)

	#### dihedral rotationfor H
	options.rot_axish, options.rotmat_idxh=get_h_rotation_axis(atoms, bonds, h_ref)
	print(f"  total {len(options.rot_axish)} angles for H rotation")
	
	#### do not consider collision between atoms that are 3 bonds apart
	maxlen=3
	npt=npt_h+npt_noh
	bd=bonds_h[:,:2].astype(int)
	bonds_matrix=scipysparse.csr_matrix((np.ones(len(bd)), (bd[:,0], bd[:,1])), shape=(npt,npt))

	#### since dijkstra return full matrix, we do this piece by piece to avoid CPU memory issues
	options.connect_all=[]
	for i in range(0,npt, 5000):
		d = scipysparse.csgraph.dijkstra(bonds_matrix, directed=False, limit=maxlen, indices=np.arange(i,min(i+5000, npt)))
		options.connect_all.extend([np.where(i<=maxlen)[0] for i in d])
		print(len(options.connect_all),npt, end='\r')	
	
	print()
	
	if options.load and os.path.isfile(wfile2):
		gen_model_full.load_weights(wfile2)
	
	options.clash_nb=128
	
	#### deal with clashing...
	clashid=calc_clashid(atom_pos_h[0].numpy(), options, pad=60)

	vdw_radius=tf.gather(options.vdwr_h, clashid)+options.vdwr_h[:,None]
	atomdic={'H':0,'C':1,'N':2,'O':3,'S':4,'P':4,'M':9}
	atype=np.array([atomdic[a.id[0]] for a in options.atoms])
	atype=np.append(atype, np.zeros(len(options.h_info[0]), dtype=int))

	ah0=options.h_info[1][:,0]
	ah0=(atype[ah0]==1).astype(int)
	atype[options.npt_noh:]+=ah0*9
	options.atype=atype

	options.clashid=clashid
	options.vdw_radius=vdw_radius
	
	
	#### consider more points for the clashing of moving domain
	hi=options.h_info[1][:,0]
	m0=imsk>.5
	m1=imsk.numpy()[hi]>.5
	m2=np.concatenate([m0, m1])
	pts_sub=np.where(m2>0)[0]
	
	print("Starting full model refinement...")
	niter=5000*niter[2]
	checkpoint=[0, 500, 2000, 8000]
	c0=len(cost)+niter
	for itr in range(niter):
		
		if itr in checkpoint:
			
			conf=mid2
			pout=gen_model(conf, training=False)
			pout=pout+gen_model_ca(conf, training=False)
			pout=pout*imsk[None,:,None]
			pout=pout+gen_model_full(conf, training=False)    
			pout+=pts
			atom_pos=(pout[:,:,:3]*[1,-1,-1]+0.5)*options.apix*options.maxboxsz
			atom_pos_h=add_h(atom_pos, options.h_info)
			
			print("\nClash indices for full model")
			clashid0, vdwr0, omask0=calc_clashid_multi(atom_pos_h, options)
			
			if options.mask!=None:
				print("Clash indices for moving domain")	
				clashid1, vdwr1, omask1=calc_clashid_multi(atom_pos_h, options, nnb=128*3, subset=pts_sub)
# 
# 			print("conf, clash0, clash1")
# 			nclash1=0
# 			for i in range(len(mid2)):
# 				clash=find_clash(atom_pos_h[i][None,:], options, clashid=clashid0, subset=[], clashomask=omask0, vdw=vdwr0)
# 				nclash=np.sum(clash.numpy()>0)//clash.shape[0]
# 				
# 				if options.mask!=None:
# 					clash1=find_clash(atom_pos_h[i][None,:], options, clashid=clashid1, subset=pts_sub, clashomask=omask1, vdw=vdwr1)
# 					nclash1=np.sum(clash1.numpy()>0)//clash1.shape[0]
# 					
# 				print(i, nclash, nclash1)

		
		with tf.GradientTape() as gt:
			
			if options.ndim==1:
				a=tf.random.uniform((options.batchsz,1))*2-1
				a*=np.max(mid2)
				conf=tf.repeat(a,4,axis=1)
				
			elif options.ndim==2:
				r=mid2[0,0]
				a=tf.random.uniform((options.batchsz,1))*np.pi*2
				conf=r*tf.concat([tf.sin(a), tf.sin(a), tf.cos(a), tf.cos(a)],axis=1)
			
			pout=gen_model(conf, training=False)
			pout=pout+gen_model_ca(conf, training=False)
			
			pout=pout*imsk[None,:,None]
			# print(conf.shape, pout.shape)
			# pout=pout+gen_model_full(conf, training=False)
			pout=pout+gen_model_full(conf, training=True)       
			pout+=pts
			atom_pos=(pout[:,:,:3]*[1,-1,-1]+0.5)*options.apix*options.maxboxsz
			
			lossetc=0

			######
			bond_len=calc_bond(atom_pos, options.bonds[:,:2].astype(int))
			bond_df=(bond_len-options.bonds[:,2])/options.bonds[:,3]
			bond_score=tf.reduce_mean(tf.exp(-5*bond_df**2))
			bond_outlier=tf.reduce_mean(tf.maximum(0,abs(bond_df)-options.nstd_bond))*50
			# bond_outlier+=tf.reduce_mean(tf.maximum(0,-bond_df-options.nstd_bond*.8))*50
			lossetc+=bond_score
			lossetc+=bond_outlier

			######
			ang_val=calc_angle(atom_pos, options.angle[:,:3].astype(int))
			ang_df=(ang_val-options.angle[:,3])/options.angle[:,4]
			ang_score=1-tf.reduce_mean(tf.exp(-8*ang_df**2))
			ang_outlier=tf.reduce_mean(tf.maximum(0,abs(ang_df)-options.nstd_angle))*1000*20
			lossetc+=ang_score
			lossetc+=ang_outlier

			######
			pt=tf.gather(atom_pos, options.idx_dih_rama, axis=1)
			phi=calc_dihedral_tf(pt[:,:,:4])
			psi=calc_dihedral_tf(pt[:,:,4:])
			rama=eval_rama(phi, psi, options)
			rama_score=tf.reduce_mean(rama)*.1
			rama_outlier=tf.reduce_mean(tf.maximum(0,rama-options.rama_thr0))*500
			rama_outlier+=tf.reduce_mean(tf.maximum(0,rama-options.rama_thr1))*1000*1000*1
			lossetc+=rama_score
			lossetc+=rama_outlier

			##########
			pt=tf.gather(atom_pos, options.idx_dih_plane, axis=1)
			rot=calc_dihedral_tf(pt)
			rot=tf.sin(rot*np.pi/180.)
			rot=tf.maximum(0, abs(rot)-options.thr_plane)
			plane_score=tf.reduce_mean(rot)*1000

			pt=tf.gather(atom_pos, options.idx_dih_piptide, axis=1)
			rot=calc_dihedral_tf(pt)
			rot=tf.sin(rot*np.pi/180.)
			rot=tf.maximum(0, abs(rot)-options.thr_piptide)
			plane_score+=tf.reduce_mean(rot)*1000

			lossetc+=plane_score            

			##########
			rota_out=[]
			for chin in range(4):
				ii=options.chi_idx[chin].T.flatten()
				ii_mat=options.chi_mat[chin][None,...]

				ii=options.idx_dih_chi[ii][:,:4]
				pt=tf.gather(atom_pos, ii, axis=1)
				dih=calc_dihedral_tf(pt)%360
				dih=tf.reshape(dih, (atom_pos.shape[0], chin+1, -1))
				dih=tf.transpose(dih, (0,2,1))

				d=dih[:,:,None,:]-ii_mat[:,:,:,:chin+1]
				d=d/ii_mat[:,:,:,chin+1:chin*2+2]
				d=tf.reduce_sum(d**2, axis=-1)

				d=tf.exp(-d)*ii_mat[:,:,:,-1]
				d=tf.reduce_sum(d, axis=-1)
				d=tf.maximum(0,d-.05)

				rota_out.append(d)

			rota_out=1-tf.concat(rota_out, axis=1)            
			rota_score=tf.reduce_mean(rota_out)*5

			r1=tf.maximum(0, rota_out-99/100.)
			# r2=tf.maximum(0, rota_out-98/100.)
			rota_outlier=tf.reduce_mean(r1)*5000
			# rota_outlier+=tf.reduce_mean(r2)*10

			lossetc+=rota_score
			lossetc+=rota_outlier


			atom_pos_h=add_h(atom_pos, options.h_info)
			clash0=find_clash(atom_pos_h, options, clashid=clashid0, subset=[], clashomask=omask0, vdw=vdwr0)			
			clash_score=(tf.reduce_sum(tf.sign(clash0)*.1+clash0))/conf.shape[0]/2.*5.
			
			if options.mask!=None:
				clash1=find_clash(atom_pos_h, options, clashid=clashid1, subset=pts_sub, clashomask=omask1, vdw=vdwr1)
			
				clash_score+=tf.reduce_sum(clash1)/conf.shape[0]/2.*5.
			# nclash1=np.sum(clash1.numpy()>0)//clash1.shape[0]
			
			lossetc+=clash_score
			l=tf.math.log(lossetc)


		assert np.isnan(l.numpy())==False
		nclash=np.sum(clash0.numpy()>0)//conf.shape[0]
		if options.mask!=None: nclash+=np.sum(clash1.numpy()>0)//conf.shape[0]

		grad=gt.gradient(l, wts)
		optimizer.apply_gradients(zip(grad, wts))
		etc=""
		etc+=f", bond {bond_score:.3f},{bond_outlier:.3f}"
		etc+=f", angle {ang_score:.3f},{ang_outlier:.3f}"
		etc+=f", rama {rama_score:.3f},{rama_outlier:.3f}"
		etc+=f", clash {clash_score:.3f},{nclash:d}"
		etc+=f", rota {rota_score:.3f},{rota_outlier:.3f}"
		etc+=f", plane {plane_score:.3f}"


		print("{}/{}\t{:.3f}{}".format(len(cost), niter, l, etc), end='\r')
		cost.append(l) 
	
	print()
	
	conf=mid2

	pout=gen_model(conf, training=False)
	pout=pout+gen_model_ca(conf, training=False)
	pout=pout*imsk[None,:,None]
	pout=pout+gen_model_full(conf, training=False)    
	pout+=pts

	atom_pos=(pout[:,:,:3]*[1,-1,-1]+0.5)*options.apix*options.maxboxsz
	atom_pos_h=add_h(atom_pos, options.h_info)
	
	print(pout.shape, atom_pos_h.shape)
	for i,pp in enumerate(atom_pos_h):
		save_model_pdb(pp[None,:], options, f"{path}/fit01_flex2_{i:02d}")
	
	if os.path.isfile(wfile2): os.remove(wfile2)
	gen_model_full.save_weights(wfile2)

	E2end(logid)
	

def calc_clashid_multi(atom_pos_h, options, nnb=-1, subset=[]):

	clids=[]
	cldis=[]
	atype=options.atype
	for ii, ap in enumerate(atom_pos_h):
		clashid=calc_clashid(ap.numpy(), options, pad=60, nnb=nnb, subset=subset)
		if len(subset)==0:
			vdw_radius=tf.gather(options.vdwr_h, clashid)+options.vdwr_h[:,None]
		else:
			vdw_radius=tf.gather(options.vdwr_h[subset], clashid)+options.vdwr_h[subset,None]

		ic=np.arange(len(clashid))
		ic=np.repeat(ic[:,None], clashid.shape[1], axis=1)
		ab=atype[clashid]*10+atype[ic]
		clash_omask=np.logical_or(ab==3, ab==30)
		clash_omask=clash_omask.astype(floattype)*.4

		clash=find_clash(ap[None,:], options, clashid=clashid, subset=subset, clashomask=clash_omask, vdw=vdw_radius, relu=False)
		# clash=find_clash(ap[None,:], options, relu=False)
		
		clids.append(clashid)
		cldis.append(clash[0].numpy())
		nclash=np.sum(clash.numpy()>0)//clash.shape[0]
		
	clid=np.concatenate(clids, axis=1)
	cld=np.concatenate(cldis, axis=1)
	ccs=[]
	for ii in range(len(clid)):
		cc=np.unique(clid[ii])
		if len(cc)==options.clash_nb:
			ccs.append(cc)
			continue
		ccmax=[]
		for c in cc:
			ci=clid[ii]==c
			d=cld[ii][ci]
			ccmax.append(np.max(d))

		cc=cc[np.argsort(-np.array(ccmax))][:options.clash_nb]
		ccs.append(cc)
		
	clashid=np.array(ccs)
	if len(subset)==0:
		vdwr=tf.gather(options.vdwr_h, clashid)+options.vdwr_h[:,None]
	else:
		vdwr=tf.gather(options.vdwr_h[subset], clashid)+options.vdwr_h[subset,None]

	
	ic=np.arange(len(clashid))
	ic=np.repeat(ic[:,None], clashid.shape[1], axis=1)
	ab=atype[clashid]*10+atype[ic]
	clash_omask=np.logical_or(ab==3, ab==30)
	clash_omask=clash_omask.astype(floattype)*.4
	
	return clashid, vdwr, clash_omask

if __name__ == '__main__':
	main()
	
