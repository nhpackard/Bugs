//  random number macros - november 28, 2004
//  based on mac rand() which returns integer between 0 and 32767
//  same constants are used in the standard C generator
//  these constants generate one long cycle, all possible
//  long integer values are visited exactly once.
//  try and speed up by making rand() function a macro...
//  this version tries not performing the right shift,
//  just the floating point conversion and multiplication...
//  declaring x a double actually runs no slower
//  also if x is a float there is a small probability that
//  f_rand() will return 1.0  (probability is 128/4294967296).
//  for ultimate speed, redeclare seed in body of code:
//  register unsigned long _seed = 1;
//  if random numbers generated in several functions, have to
//  keep _seed static to preserve seed from one call to the next...
//  note first call e.g. of my_rand() just returns the seed
//  putting the constants in R1 and R2 gets us a 5% speedup...

//static unsigned long int _seed = 1;
extern unsigned long int _seed;
static unsigned long int _R1 = 1103515245, _R2 = 12345;

/*  basic linear congruential operator  */	
#define myrand()	\
	_seed = _seed * _R1 + _R2
/*  return raw unsigned long  */
#define my_rand()	\
	_seed;		\
	myrand()
/*  return short between 0 and 65535  */
#define s_rand()	\
	(_seed>>16);		\
	myrand()
/*  return short between 0 and n-1  */
#define n_rand(n)	\
	(n*(_seed>>16) >> 16);	\
	myrand()
/*  return short between 0 and 7  */
#define n_rand8()	\
	(_seed >> 29);	\
	myrand()

#define RFACT 1.0/4294967296.0
#define R1FACT 2.0/4294967296.0
#define ANGFACT 2.0*3.1415926536/4294967296.0
/*  return floats between 0 and 1  */
#define f_rand()	\
	RFACT*_seed;		\
	myrand()
/*  return floats between -1 and 1  */
#define f1_rand()	\
	(R1FACT*_seed-1.0);		\
	myrand()
/*  return floats between 0 and 2pi  */
#define ang_rand()	\
	ANGFACT*_seed;		\
	myrand()
