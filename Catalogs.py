'''Keep track of Catalogs of objects, usually stars.'''
from imports import *
import settings, relations
import matplotlib.animation
from astroquery.vizier import Vizier
import Lightcurve

def makeCatalog(**kwargs):
	'''Use keywords to select a kind of Catalog, enter its parameters, and construct the necessary catalog.'''
	name = kwargs['name']
	if name.lower() == 'testpattern':
		cat = TestPattern(**kwargs)
	elif name.lower() == 'ucac4':
		cat = UCAC4(**kwargs)
	else:
		star = zachopy.star.SingleStar(name)
		kwargs['ra'], kwargs['dec'] = star.icrs.ra.deg, star.icrs.dec.deg
		cat = UCAC4(**kwargs)
	return cat



class Star(object):
	'''a Star object, containing at least RA + Dec + magnitude'''
	def __init__(self, ra=0.0, dec=0.0, tmag=10.0, **kwargs):

		self.coord = astropy.coordinates.ICRS(ra=ra, dec=dec, unit=(astropy.units.deg,astropy.units.deg))
		self.ra = ra
		self.dec = dec
		self.tmag = tmag
		for k in kwargs.keys():
			self.__dict__[k] = kwargs[k]

class Catalog(Talker):
	'''an object to keep track of lots of stars'''
	def __init__(self):
		# decide whether or not this Catalog is chatty
		Talker.__init__(self, mute=False, pithy=False)

	def addLCs(self, magmax=None, fmax=1.0, seed=None, **kw):
		'''populate a catalog with light curves'''

		np.random.seed(seed)
		# total number of stars we need to deal with
		ntotal = len(self.tmag)

		# make sure everything is at least populated as a constant
		constant = Lightcurve.constant()
		self.lightcurves = np.array([constant]*ntotal)

		# make sure that the maximum magnitude for variable stars is defined
		if magmax is None:
			magmax = np.max(self.tmag) + 1

		# pull only the stars that pass the brightness cut
		brightenough = (self.tmag <= magmax).nonzero()[0]
		nbrightenough = len(brightenough)
		self.speak('{0} stars are brighter than {1}; populating {2:.1f}% of them with light curves'.format(nbrightenough, magmax, fmax*100))

		# use the input seed, to ensure it wor
		for i in np.random.choice(brightenough, len(brightenough)*fmax, replace=False):
			self.lightcurves[i] = Lightcurve.random(**kw)

	@property
	def lightcurvecodes(self):
		return [lc.code for lc in self.lightcurves]

	def arrays(self):
		'''return (static) arrays of positions, magnitudes, and effective temperatures'''
		return self.ra, self.dec, self.tmag, self.temperature

	def snapshot(self, bjd=None, epoch=None, exptime=0.5/24.0):
		'''return a snapshot of positions, magnitudes, and effective temperatures (all of which may be time-varying)'''

		# propagate proper motions
		if bjd is not None:
			epoch = (bjd - 2451544.5)/365.25 + 2000.0
		else:
			bjd = (epoch - 2000.0)*365.25 + 2451544.5

		ra, dec = self.atEpoch(epoch)

		# determine brightness of star
		try:
			moment = np.array([lc.integrated(bjd, exptime) for lc in self.lightcurves]).flatten()
		except AttributeError:
			moment = np.array([0.0])
		tmag = self.tmag + moment

		# determine color of star
		temperature = self.temperature
		assert(ra.shape == tmag.shape)
		return ra, dec, tmag, temperature


	def atEpoch(self, epoch):

		# how many years since the catalog's epoch?
		timeelapsed = epoch - self.epoch	# in years
		self.speak('projecting catalog {0:.3f} years relative to {1:.0f}'.format(timeelapsed, self.epoch))
		# calculate the dec
		decrate = self.pmdec/60.0/60.0/1000.0	# in degrees/year (assuming original was in mas/year)
		decindegrees = self.dec + timeelapsed*decrate

		# calculate the unprojected rate of RA motion, using the mean declination between the catalog and present epoch
		rarate = self.pmra/60.0/60.0/np.cos((self.dec + timeelapsed*decrate/2.0)*np.pi/180.0)/1000.0	# in degress of RA/year (assuming original was *projected* mas/year)
		raindegrees = self.ra + timeelapsed*rarate

		# return the current positions
		return raindegrees, decindegrees


	def plot(self, epoch=2018.0):
		plt.ion()
		plt.figure('star chart')
		try:
			self.ax.cla()
		except:
			self.ax = plt.subplot()
		ra, dec, tmag, temperature = self.snapshot(epoch=epoch)
		deltamag = 20.0 - tmag
		size = deltamag**2*5
		try:
			self.plotdata.set_data(ra, dec)
		except:
			self.plotdata = self.ax.scatter(ra, dec, s=size, marker='o', color='grey', alpha=0.3, edgecolors='black')
		#for i in range(len(ra)):
		#	self.ax.text(ra[i], dec[i], '{0:.2f}'.format(tmag[i]),horizontalalignment='center', verticalalignment='center', alpha=0.5, size=8, color='green',weight='bold')
		self.ax.set_aspect(1)
		self.ax.set_xlabel('Right Ascension')
		self.ax.set_ylabel('Declination')
		self.ax.set_title('{0} at epoch {1}'.format(self.__class__.__name__, epoch))
		self.ax.set_xlim(np.min(self.ra), np.max(self.ra))
		self.ax.set_ylim(np.min(self.dec), np.max(self.dec))
		plt.draw()

	def movie(self, epochs=[1950,2050], bitrate=10000):
		metadata = dict(artist='Zach Berta-Thompson (zkbt@mit.edu)')
		self.writer = matplotlib.animation.FFMpegWriter(fps=30, metadata=metadata, bitrate=bitrate)

		self.plot(np.min(epochs))
		f = plt.gcf()
		filename=settings.dirs['plots'] + 'testcatalogpropermotions.mp4'
		with self.writer.saving(f, filename, 100):
			for e in np.linspace(epochs[0], epochs[1], 20):
				self.speak('{0}'.format(e))
				self.plot(e)
				self.writer.grab_frame()
		self.speak('saved movie to {0}'.format(filename))

	def writeProjected(self, ccd=None, outfile='catalog.txt'):
		# take a snapshot projection of the catalog
		ras, decs, tmag, temperatures = self.snapshot(ccd.bjd,
										exptime=ccd.camera.cadence/60.0/60.0/24.0)

		# calculate the CCD coordinates of these stars
		stars = ccd.camera.cartographer.point(ras, decs, 'celestial')
		x,y = stars.ccdxy.tuple

		basemag = self.tmag
		lc = self.lightcurvecodes
		t = astropy.table.Table(data= [ras, decs, x, y, basemag, lc],
								names=['ra', 'dec', 'x', 'y', 'tmag', 'lc'])
		t.write(outfile, format='ascii.fixed_width', delimiter=' ')
		self.speak("save projected star catalog {0}".format(outfile))


class TestPattern(Catalog):
	'''a test pattern catalog, creating a grid of stars to fill an image'''
	def __init__(self, **kwargs):
		'''create a size x size square (in arcsecs) test pattern of stars,
		with spacing (in arcsecs) between each element and
		magnitudes spanning the range of magnitudes'''
		Catalog.__init__(self)
		self.load(**kwargs)

	def load(self, size=3000.0, spacing=200.0, magnitudes=[6,16], ra=0.0, dec=0.0, random=False, nudge=21.1, pm=0.0, **kwargs):

		self.name = 'testpattern_{0:.0f}to{1:.0f}'.format(np.min(magnitudes), np.max(magnitudes))
		# how many stars do we need?
		pixels = np.maximum(np.int(size/spacing), 1)
		n = pixels**2

		# construct a linear grid of magnitudes
		self.tmag = np.linspace(np.min(magnitudes), np.max(magnitudes),n)[::-1]
		ras, decs = np.meshgrid(np.arange(pixels)*spacing, np.arange(pixels)*spacing)
		self.dec = ((decs - np.mean(decs))/3600.0 + dec).flatten()
		self.ra = (ras - np.mean(ras)).flatten()/np.cos(self.dec*np.pi/180.0)/3600.0 + ra
		if random:
			self.tmag = np.random.uniform(np.min(magnitudes), np.max(magnitudes), n)
			offset = nudge*(np.random.rand(2, n) - 0.5)/3600.0
			self.dec += offset[0,:]
			self.ra += offset[1,:]

		if pm > 0:
			self.pmra, self.pmdec = np.random.normal(0,pm,n), np.random.normal(0,pm, n)
		else:
			self.pmra, self.pmdec = 0, 0
		self.epoch = 2018.0
		self.temperature = 5800.0 + np.zeros_like(self.ra)


class UCAC4(Catalog):
	def __init__(self, ra=0.0, dec=90.0, radius=0.2, write=True, faint=10, **kwargs):
		Catalog.__init__(self)
		self.load(ra=ra, dec=dec, radius=radius, write=write)

	def load(self, ra=0.0, dec=90.0, radius=0.2, write=True):

		# select the columns that should be downloaded from UCAC
		catalog = 'UCAC4'
		ratag = '_RAJ2000'
		dectag = '_DEJ2000'
		if catalog=='UCAC4':
			vcat = 'I/322A/out'
			rmagtag ='f.mag'
			jmagtag = 'Jmag'
			vmagtag = 'Vmag'
			pmratag, pmdectag = 'pmRA', 'pmDE'
			columns = ['_RAJ2000','_DECJ2000','pmRA', 'pmDE','f.mag','Jmag', 'Vmag']

		# create a query through Vizier
		v = Vizier(catalog=vcat,columns=columns)
		v.ROW_LIMIT = -1

		# either reload an existing catalog file or download to create a new one
		starsfilename = settings.prefix + 'intermediates/' +  "{catalog}_{ra}_{dec}_{radius}".format(catalog=catalog, ra=ra, dec=dec, radius=radius).replace(' ', '') + '.npy'
		try:
			t = np.load(starsfilename)
			self.speak("loading a catalog of stars from {0}".format(starsfilename))
		except:
			self.speak("querying {catalog} for ra = {ra}, dec = {dec}, radius = {radius}".format(catalog=catalog, ra=ra, dec=dec, radius=radius))
			t = v.query_region(astropy.coordinates.ICRS(ra=ra, dec=dec, unit=(astropy.units.deg,astropy.units.deg)), radius='{:f}d'.format(radius), verbose=True)[0]
			np.save(starsfilename, t)

		self.table = astropy.table.Table(t)

		ras = np.array(t[:][ratag])
		decs = np.array(t[:][dectag])
		pmra = np.array(t[:][pmratag])
		pmdec = np.array(t[:][pmdectag])
		rmag = np.array(t[:][rmagtag])
		jmag = np.array(t[:][jmagtag])
		vmag = np.array(t[:][vmagtag])

		rbad = (np.isfinite(rmag) == False)*(np.isfinite(vmag))
		rmag[rbad] = vmag[rbad]
		rbad = (np.isfinite(rmag) == False)*(np.isfinite(jmag))
		rmag[rbad] = jmag[rbad]

		jbad = (np.isfinite(jmag) == False)*(np.isfinite(vmag))
		jmag[jbad] = vmag[jbad]
		jbad = (np.isfinite(jmag) == False)*(np.isfinite(rmag))
		jmag[jbad] = rmag[jbad]

		vbad = (np.isfinite(vmag) == False)*(np.isfinite(rmag))
		vmag[vbad] = rmag[vbad]
		vbad = (np.isfinite(vmag) == False)*(np.isfinite(jmag))
		vmag[vbad] = jmag[vbad]



		temperatures = relations.pickles(rmag-jmag)
		imag = rmag - relations.davenport(rmag-jmag)



		pmra[np.isfinite(pmra) == False] = 0.0
		pmdec[np.isfinite(pmdec) == False] = 0.0

		ok = np.isfinite(imag)
		self.speak("found {0} stars with {1} < V < {2}".format(np.sum(ok), np.min(rmag[ok]), np.max(rmag[ok])))
		self.ra = ras[ok]
		self.dec = decs[ok]
		self.pmra = pmra[ok]
		self.pmdec = pmdec[ok]
		self.tmag = imag[ok]
		self.temperature = temperatures[ok]
		self.epoch = 2000.0
		#return ras[ok], decs[ok], rmag[ok], jmag[ok], imag[ok], temperatures[ok]

class Trimmed(Catalog):
	'''a trimed catalog, created by removing elements from another catalog'''
	def __init__(self, inputcatalog, keep):
		'''inputcatalog = the catalog to start with
		keep = an array indices indicating which elements of inputcatalog to use'''

		Catalog.__init__(self)
		# define the keys to propagate from old catalog to the new one
		keystotransfer = ['ra', 'dec', 'pmra', 'pmdec', 'tmag', 'temperature', 'lightcurves']

		for k in keystotransfer:
			self.__dict__[k] = inputcatalog.__dict__[k][keep]

		self.epoch = inputcatalog.epoch
