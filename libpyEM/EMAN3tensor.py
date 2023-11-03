#!/usr/bin/env python
#
# Author: Steven Ludtke, 05/19/2023 (sludtke@bcm.edu)
# Copyright (c) 2000-2023 Baylor College of Medicine
#
# This software is issued under a joint BSD/GPL license. You may use the
# source code in this file under either license. However, note that the
# complete EMAN2 and SPARX software packages have some GPL dependencies,
# so you are responsible for compliance with the licenses of these packages
# if you opt to use BSD licensing. The warranty disclaimer below holds
# in either instance.
#
# This complete copyright notice must be included in any revised version of the
# source code. Additional authorship citations may be added, but existing
# author citations must be preserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston MA 02111-1307 USA
#

"""
ONLY import this file if you will be working with tensorflow in your program, otherwise the tensorflow initialization may add unreasonable startup delays

This module contains EMAN3-specific operations. We don't generate EMAN-like aliases for monolithic tensorflow operations. With that in mind:
Some useful TensorFlow/NumPy operations/comments in an EMAN3 context which are not part of the module:

VERY important to note that when indexing EMData objects it is emd[x,y,z], whereas indexing numpy/tensorflow objects, the last index is the fastest varying ary[z,y,x] !

tf.signal.rfft2d    - returns a new constant tensor which is the FFT of the last 2 indices of the tensor.
                       ie - if used on a 3-D tensor (N,X,Y) will return (N,FX,FY)
                       FFT tensors are complex, and padded in X, ie (NX,NY) -> (NX/2+1,NY)

tf.signal.irfft2d   - the inverse operation

np.fromfunction(lambda x,y: np.hypot(x,y),(nx,ny)) - for example

"""

from EMAN3 import *
import tensorflow as tf
import numpy as np


class EMDataStack():
	"""This class represents a stack of EMData images with an (optional) tensorflow/numpy representation.
	- All images in the stack must have the same dimensions.
	- Adding new EMData objects or setting an existing object to a different object will force the tensorflow and numpy representations to be regenerated
	- WARNING: the Tensorflow representation will be generated the first time it is accessed. Image changes to any contained EMData objects after this point will
	not be reflected in the tensor unless the update() method is called.

	EMData elements may be accessed as stack[n], and elements may similarly be altered
	"""

	def __init__(self,imgs=None):
		"""	imgs - one of:
		None
		filename, with optional ":" range specifier (see https://eman2.org/ImageFormats)
		single EMData object
		list or tuple of EMData objects
		"""
		self.set_data(imgs)

	def set_data(self,imgs):
		""" """
		if imgs is None: self._stack=[]
		elif isinstance(imgs,EMData): self._stack=[imgs]
		elif isinstance(imgs,str): self._stack=EMData.read_images(imgs)
		else:
			try: self._stack=list(imgs)		# copy the list, not the elements of the list
			except: raise Exception("EMDataStack may only be initialized with None, a filename, an EMData object or a list/tuple of EMData objects")

		self._tensor=None
		self._numpy=None

	def __len__(self): return len(self._stack)

	def __getitem__(self,key): return self._stack[key]

	def __setitem__(self,key,value):
		self._stack[key]=value
		self._tensor=None
		self._numpy=None

	def update(self):
		"""Call this if any of the contained EMData objects are altered (image values) to trigger regeneration of the tensor upon next use. Not necessary
	to call this if you alter which image objects are contained in the stack."""
		self._tensor=None

	@property
	def tensor(self):
		"""Returns the current tuple of EMData objects as a single constant tensor such that tensor[i] will produce the tensor form of self.stack[i]"""
		if self._tensor is None:
			if len(self._stack)==0: raise Exception("EMDataStack cannot provide numpy representation until it has been initialized with data")
			self._tensor=tf.constant(np.stack(self.numpy,axis=0))
		return self._tensor

	@tensor.setter
	def tensor(self,value):
		if value is not None: raise Exception("EMDataStack.tensor may not be set to any value other than None. It is generated automatically on demand.")
		self._tensor=None

	@property
	def numpy(self):
		"""Returns a list of numpy objects created from the EMData objects (thus they share memory). Due to memory sharing, the stack is not automatically
		merged into a single numpy array. This could be done with, for example np.stack(stk.numpy,axis=0), but the shared memory aspect would be lost.
		"""
		if self._numpy==None:
			if len(self._stack)==0: raise Exception("EMDataStack cannot provide numpy representation until it has been initialized with data")
			self._numpy=[to_numpy(im) for im in self._stack]
		return self._numpy

	@numpy.setter
	def numpy(self,value):
		if value is not None: raise Exception("EMDataStack.numpy may not be set to any value other than None. It is generated automatically on demand.")
		self._numpy=None

def Orientations():
	"""This represents a set of orientations, with a standard representation of an XYZ vector where the vector length indicates the amount
		of rotation with a length of 0.5 corresponding to 180 degrees. This form is a good representation for deep learning minimization strategies
		which conventionally span a range of ~1.0. This form can be readily interconverted to EMAN2 Transform objects or transformation matrices
		for use with Gaussians.
	"""

	def __init__(self,xyzs=0):
		"""Initialize with either the number of orientations or a N x 3 matrix"""
		if isinstance(xyzs,int):
			if xyzs<=0: self._data=None
			else: self._data=np.zeros((xyzs,3))
		else:
			try: self._data=np.array(xyzs)
			except: raise Exception("Orientations must be initialized with an integer (number of orientations) or a N x 3 numpy array")

	def __getitem__(self,key):
		"""Return the keyed Gaussian parameter, may return a tensor or numpy array. G[i] returns the 4-vector for the i'th Gaussian"""
		return self._data[key]

	def __setitem__(self,key,value):
		# if the Gaussians are a tensor, we turn it back into numpy for modification
		if isinstance(self._data,tf.Tensor): self._data=self._data.numpy()
		self._data[key]=value

	def to_mx(self):
		"""Returns the current set of orientations as a N x 2 x 3 matrix which will transform a set of 3-vectors to a set of
		2-vectors, ignoring the resulting Z component. Typically used with Gaussians to generate projections."""
		if not isinstance(self._data,tf.Tensor): self._data=tf.constant(self._data)

		l=tf.norm(xyz)
		w=cos(pi*l)  # cos "real" component of quaternion
		if l>0:
			s=sin(pi*l)/l  # multiply xyz component of quaternion by this
			q=xyz*s        # the x/y/z components of q
		else: q=xyz

		mx=np.array(((1-2*(q[1]*q[1]+q[2]*q[2]),2*q[0]*q[1]-2*q[2]*w,2*q[0]*q[2]+2*q[1]*w),
			(2*q[0]*q[1]+2*q[2]*w,1-(2*q[0]*q[0]+2*q[2]*q[2]),2*q[1]*q[2]-2*q[0]*w)))

def Gaussians():
	"""This represents a set of Gaussians with x,y,z,amp parameters (but no width). Main representation is a N x 4 numpy array (x,y,z,amp) ],
but tensorflow can be used for some operations"""

	def __init__(self,gaus=0):
		if isinstance(gaus,int):
			if gaus<=0: self._data=None
			else: self._data=np.zeros((gaus,4))
		else:
			try: self._data=np.array(gaus)
			except: raise Exception("Gaussians must be initialized with an integer (number of Gaussians) or N x 4 matrix")

	def __getitem__(self,key):
		"""Return the keyed Gaussian parameter, may return a tensor or numpy array. G[i] returns the 4-vector for the i'th Gaussian"""
		return self._data[key]

	def __setitem__(self,key,value):
		# if the Gaussians are a tensor, we turn it back into numpy for modification
		if isinstance(self._data,tf.Tensor): self._data=self._data.numpy()
		self._data[key]=value

	def spinvec_to_mx(self,xforms):
		"""This will convert an Nx3 array of "spin vectors" into an Nx4x2 tensor, which may be re-used
		to rotate a set of Gaussian points into many different 2-D projection orienations for use with
		to_tfimages(). The spin vector is an x/y/z vector where the vector direction denotes the spin
		axis and the length of the vector denotes the amount of rotation. A length of 1 will correspond
		to a 2*pi rotation to make it more compatible with deep learning. This is very similar to a
		quaternion, and can be easily converted into one by converting the X/Y/Z vector length:
		len'=sin(2*pi*len/2) and computing a w such that the quaternion has unit length"""
		pass


	def to_tfimages(self,mx):
		pass


def tf_set_device(dev=0,maxmem=4096):
	"""Sets maximum memory for a specific Tensorflow device and returns a device to use with "with:"
	dev - GPU number or -1 for CPU (CPU doesn't actually permit memory size allocation)
	maxmem - maximum memory to allocate in megabytes

	dev=tf_set_device(gpuid,6144)
	with dev:
		# tensorflow operations, "with" block optional
	"""
	if dev<0 :
		pdevice=tf.config.list_physical_devices('CPU')[0]
		tf.config.set_logical_device_configuration(pdevice,[tf.config.LogicalDeviceConfiguration()])
		return tf.device('/CPU:0')
	else:
		pdevice=tf.config.list_physical_devices('GPU')[dev]
		tf.config.set_logical_device_configuration(pdevice,[tf.config.LogicalDeviceConfiguration(memory_limit=maxmem)])
		return tf.device(f'/GPU:{dev}')

def from_tf(tftensor,stack=False):
	"""Convert a specified tensor to an EMData object
	If stack is set, then the first axis of the tensor will be unpacked to form a list. ie a 3D tensor would become a list of 2D EMData objects"""

	if stack:
		return [EMNumPy.numpy2em(tftensor[i].numpy()) for i in range(tftensor.shape[0])]
	return EMNumPy.numpy2em(tftensor.numpy())

def to_tfvar(emdata):
	"""Convert a specified EMData object or list of EMData objects into a TensorFlow Variable. WARNING many tensorflow operations are very inefficient with Variable tensors!"""
	if isinstance(emdata,EMData):
		return tf.Variable(EMNumPy.em2numpy(emdata))

	if isinstance(emdata,list) or isinstance(emdata,tuple):
		npstack=np.stack([to_numpy(im) for im in emdata],axis=0)
		return tf.Variable(npstack)

def to_tf(emdata):
	"""Convert a specified EMData object or list of EMData objects into a Tensorflow constant tensor. The tensor is immutable, but will have much better performance for most operations."""

	if isinstance(emdata,EMData):
		return tf.constant(EMNumPy.em2numpy(emdata))

	if isinstance(emdata,list) or isinstance(emdata,tuple):
		npstack=np.stack([to_numpy(im) for im in emdata],axis=0)
		return tf.constant(npstack)

def tf_fft2d(imgs):
	if isinstance(imgs,EMData) or ((isinstance(imgs,list) or isinstance(imgs,tuple)) and isinstance(imgs[0],EMData)): imgs=to_tf(imgs)

	if imgs.dtype==tf.complex64: raise Exception("Data type must be real")

	return tf.signal.rfft2d(imgs)

def tf_fft3d(imgs):
	if isinstance(imgs,EMData) or ((isinstance(imgs,list) or isinstance(imgs,tuple)) and isinstance(imgs[0],EMData)): imgs=to_tf(imgs)

	if imgs.dtype==tf.complex64: raise Exception("Data type must be real")

	return tf.signal.rfft3d(imgs)

def tf_ift2d(imgs):
	if isinstance(imgs,EMData) or ((isinstance(imgs,list) or isinstance(imgs,tuple)) and isinstance(imgs[0],EMData)): imgs=to_tf(imgs)

	if imgs.dtype!=tf.complex64: raise Exception("Data type must be complex")

	return tf.signal.irfft2d(imgs)

def tf_ift3d(imgs):
	if isinstance(imgs,EMData) or ((isinstance(imgs,list) or isinstance(imgs,tuple)) and isinstance(imgs[0],EMData)): imgs=to_tf(imgs)

	if imgs.dtype!=tf.complex64: raise Exception("Data type must be complex")

	return tf.signal.irfft3d(imgs)

def tf_downsample_2d(imgs,newx,stack=False):
	"""Fourier downsamples a tensorflow 2D image or stack of 2D images (similar to math.fft.resample processor conceptually)
	return will always be a stack (3d tensor) even if the first dimension is 1
	passed image/stack may be real or complex (FFT), return is always complex!
	final image will be a square/cube with the (real space) size nx on all axes. Should not be used to downsample rectangular images.
	newx specifies the real-space image size after downsampling, MUST be even, and the input image must have even dimensions in real space
	note that complex conjugate relationships aren't enforced in the cropped Fourier volume in redundant locations
	"""

	if newx%2!=0 : raise Exception("newx must be an even number")

	if isinstance(imgs,EMData) or ((isinstance(imgs,list) or isinstance(imgs,tuple)) and isinstance(imgs[0],EMData)): imgs=to_tf(imgs)

	if imgs.dtype!=tf.complex64: imgs=tf.signal.rfft2d(imgs)

	if imgs.ndim==2: imgs=tf.expand_dims(imgs,0)	# we need a 3 rank tensor

	cropy=tf.gather(imgs,np.concatenate((np.arange(newx//2),np.arange(imgs.shape[1]-newx//2,imgs.shape[1]))),axis=1)
	return cropy[:,:,:newx//2+1]

def tf_downsample_3d(imgs,newx,stack=False):
	"""Fourier downsamples a tensorflow 3D image or stack of 3D images (similar to math.fft.resample processor conceptually)
	return will always be a stack (3d tensor) even if the first dimension is 1
	passed image/stack may be real or complex (FFT), return is always complex!
	final image will be a square/cube with the size nx on all axes. Should not be used to downsample rectangular images.
	newx specifies the real-space image size after downsampling,MUST be even, and the input image must have even dimensions in real space
	note that complex conjugate relationships aren't enforced in the cropped Fourier volume
	"""

	if newx%2!=0 : raise Exception("newx must be an even number")

	if isinstance(imgs,EMData) or ((isinstance(imgs,list) or isinstance(imgs,tuple)) and isinstance(imgs[0],EMData)): imgs=to_tf(imgs)

	if imgs.dtype!=tf.complex64: imgs=tf.signal.rfft3d(imgs)

	if imgs.ndim==3: imgs=tf.expand_dims(imgs,0)	# we need a 3 rank tensor

	cropz=tf.gather(imgs,np.concatenate((np.arange(newx//2),np.arange(imgs.shape[1]-newx//2,imgs.shape[1]))),axis=1)
	cropy=tf.gather(cropz,np.concatenate((np.arange(newx//2),np.arange(imgs.shape[2]-newx//2,imgs.shape[1]))),axis=2)
	return cropy[:,:,:,:newx//2+1]

FRC_RADS={}		# dictionary (cache) of constant tensors of size ny/2+1,ny containing the Fourier radius to each point in the image
#FRC_NORM={}		# dictionary (cache) of constant tensors of size ny/2*1.414 (we don't actually need this for anything)
#TODO iterating over the images is handled with a python for loop. This may not be taking great advantage of the GPU (just don't know)
# two possible approaches would be to add an extra dimension to rad_img to cover image number, and handle the scatter_nd as a single operation
# or to try making use of DataSet. I started a DataSet implementation, but decided it added too much design complexity
def tf_frc(ima,imb):
	"""Computes the pairwise FRCs between two stacks of complex images. Returns a list of 1D FSC tensors."""
	if ima.dtype!=tf.complex64 or imb.dtype!=tf.complex64 : raise Exception("tf_fsc requires FFTs")

	global FRC_RADS
#	global FRC_NORM		# we don't actually need this unless we want to compute uncertainties (number of points at each radius)
	ny=ima.shape[1]
	nimg=ima.shape[0]
	nr=int(ny*0.70711)+1	# max radius we consider
	try:
		rad_img=FRC_RADS[ny]
#		norm=FRC_NORM[ny]
	except:
		rad_img=tf.expand_dims(tf.constant(np.vstack((np.fromfunction(lambda y,x: np.int32(np.hypot(x,y)),(ny//2,ny//2+1)),np.fromfunction(lambda y,x: np.int32(np.hypot(x,ny//2-y)),(ny//2,ny//2+1))))),2)
#		rad_img=tf.constant(np.vstack((np.fromfunction(lambda y,x: np.int32(np.hypot(x,y)),(ny//2,ny//2+1)),np.fromfunction(lambda y,x: np.int32(np.hypot(x,ny//2-y)),(ny//2,ny//2+1)))))
		FRC_RADS[ny]=rad_img
#		ones=tf.ones(ima.shape)
#		zero=tf.zeros((int(ny*0.70711)+1))
#		norm=tf.tensor_scatter_nd_add(zero, rad_img, ones)  # computes the number of values at each Fourier radius
#		FRC_NORM[ny]=norm

	imar=tf.math.real(ima) # if you do the dot product with complex math the processor computes the cancelling cross-terms. Want to avoid the waste
	imai=tf.math.imag(ima)
	imbr=tf.math.real(imb)
	imbi=tf.math.imag(imb)

	imabr=imar*imbr		# compute these before squaring for normalization
	imabi=imai*imbi

	imar=imar*imar		# just need the squared versions, not the originals now
	imai=imai*imai
	imbr=imbr*imbr
	imbi=imbi*imbi

	frc=[]
	for i in range(nimg):
		zero=tf.zeros([nr])
#		print(zero.shape,rad_img.shape,imabr[i].shape)
		cross=tf.tensor_scatter_nd_add(zero,rad_img,imabr[i])	#start with zero when we add the real component
		cross=tf.tensor_scatter_nd_add(cross,rad_img,imabi[i])	#add the imaginary component to the real

		aprd=tf.tensor_scatter_nd_add(zero,rad_img,imar[i])
		aprd=tf.tensor_scatter_nd_add(aprd,rad_img,imai[i])

		bprd=tf.tensor_scatter_nd_add(zero,rad_img,imbr[i])
		bprd=tf.tensor_scatter_nd_add(bprd,rad_img,imbi[i])

		frc.append(cross/tf.sqrt(aprd*bprd))

	return frc

FSC_REFS={}
def tf_fsc(ima,imb):
	"""Computes the FSC between a stack of complex volumes and a single reference volume. Returns a stack of 1D FSC curves."""
	if ima.dtype!=tf.complex64 or imb.dtype!=tf.complex64 : raise Exception("tf_fsc requires FFTs")


#### Project 3d Gaussian coordinates based on transforms to make projection
##   input:  pts - ( batch size, number of Gaussian, 3 (x,y,z) )
##                 ( number of Gaussian, 3) should also work
##           ang - ( batch size, 5 (az, alt, phi, tx, ty) )
#@tf.function
def xf2pts(pts, ang):

	#### input EMAN style euler angle (az, alt, phi) and make projection matrix
	##   note we need to be able to deal with a batch of particles at once
	##   so everything is in matrix form
	azp=-ang[:,0]
	altp=ang[:,1]
	phip=-ang[:,2]

	matrix=tf.stack([(tf.cos(phip)*tf.cos(azp) - tf.cos(altp)*tf.sin(azp)*tf.sin(phip)),
	(tf.cos(phip)*tf.sin(azp) + tf.cos(altp)*tf.cos(azp)*tf.sin(phip)),
	(tf.sin(altp)*tf.sin(phip)),

	(-tf.sin(phip)*tf.cos(azp) - tf.cos(altp)*tf.sin(azp)*tf.cos(phip)),
	(-tf.sin(phip)*tf.sin(azp) + tf.cos(altp)*tf.cos(azp)*tf.cos(phip)),
	(tf.sin(altp)*tf.cos(phip)),

	(tf.sin(altp)*tf.sin(azp)),
	(-tf.sin(altp)*tf.cos(azp)),
	tf.cos(altp)], 0)

	matrix=tf.transpose(matrix)
	matrix=tf.reshape(matrix, shape=[-1, 3,3]) #### Here we get a batch_size x 3 x 3 matrix

	#### rotate Gaussian positions
	##   here we try to make it also work when pts contains only the neutral model
	if len(pts.shape)>2:
		pts_rot=tf.tensordot(pts, matrix, [[2],[2]])
		pts_rot=tf.transpose(pts_rot, (0,2,1,3))

		#### the eye matrix here is mathematically unnecessary
		##   but somehow tensorflow 2.0 does not track gradient properly without it...
		##   shouldn't do much damage on the performance anyway
		e=tf.eye(pts.shape[0], dtype=bool)#.flatten()
		pts_rot=pts_rot[e]

	else:
		pts_rot=tf.tensordot(pts, matrix, [[1],[2]])
		pts_rot=tf.transpose(pts_rot, [1,0,2])

	#### finally do the translation
	tx=ang[:,3][:,None]
	ty=ang[:,4][:,None]
#	pts_rot_trans=tf.stack([(pts_rot[:,:,0]+tx), (-pts_rot[:,:,1])+ty], 2)
	pts_rot_trans=tf.stack([(-pts_rot[:,:,1])+ty,(pts_rot[:,:,0]+tx)], 2)

	#pts_rot_trans=pts_rot_trans*sz+sz/2
	return pts_rot_trans


#### make 2D projections from Gaussian coordinates in Fourier space
##   input:  pts - ( batch size, number of Gaussian, 5 (x,y,z,amp,sigma) )
##                 ( number of Gaussian, 3) should also work
##           ang - ( batch size, 5 (az, alt, phi, tx, ty) )
##        params - a dictionary of some Fourier indices for slicing
##                 sz - Fourier box size
##                 idxft - Fourier indices
##                 rrft - radial Fourier indices
##            lp - lowpass filter applied to the images
##                 this should not be necessary since we use FRC for loss
##                 but the dynamic range of values in Fourier space can sometimes be too high...
##           sym - symmetry string
#@tf.function
def pts2img(pts, ang, params, lp=.1, sym="c1"):
	bsz=ang.shape[0]
	sz, idxft, rrft=params["sz"], params["idxft"], params["rrft"]
	xfo=params["xforigin"]

	### initialize output and parse input
	imgs=tf.zeros((bsz, sz,sz), dtype=floattype)
	if len(pts.shape)>2 and pts.shape[0]>1:
		ni=pts.shape[1]
		pts=tf.reshape(pts, (-1, pts.shape[-1]))
		bamp=tf.reshape(pts[:, 3], (bsz,-1))
		multmodel=True

	else:
		bamp=pts[:, 3][None, :]
		multmodel=False

	### when a non c1 symmetry is provided, this will return a list of points
	##  one for each asymmetrical unit so we loop through them and sum the images
	p0=get_sym_pts(sym, pts)
	for p in p0:
		p=tf.transpose(p)
		if multmodel:
			p=tf.reshape(p, (bsz, ni, -1))

		## need to change from (-0.5, 0.5) to actual image coordinates
		bpos=xf2pts(p,ang)
		bpos=bpos*sz+sz/2

		bposf=tf.floor(bpos)
		bposi=tf.cast(bposf,tf.int32)	# integer index
		bposf=bpos-bposf				# remainder used for bilinear interpolation

		# messy tensor math here to implement bilinear interpolation
		bamp0=bamp*(1.0-bposf[:,:,0])*(1.0-bposf[:,:,1])	#0,0
		bamp1=bamp*(bposf[:,:,0])*(1.0-bposf[:,:,1])	#1,0
		bamp2=bamp*(bposf[:,:,0])*(bposf[:,:,1])		#1,1
		bamp3=bamp*(1.0-bposf[:,:,0])*(bposf[:,:,1])	#0,1
		bampall=tf.concat([bamp0,bamp1,bamp2,bamp3],1)
		bposall=tf.concat([bposi,bposi+(1,0),bposi+(1,1),bposi+(0,1)],1)
		imgs=tf.stack([tf.tensor_scatter_nd_add(imgs[i],bposall[i],bampall[i]) for i in range(imgs.shape[0])])

		#try: imgs=tf.tensor_scatter_nd_add(imgs,bposi,bamp)
		#except:
			#print(imgs.shape,bposi.shape,bamp.shape)
			#raise Exception

	fimgs=tf.signal.rfft2d(imgs)

	return (tf.math.real(fimgs)*xfo,tf.math.imag(fimgs)*xfo)