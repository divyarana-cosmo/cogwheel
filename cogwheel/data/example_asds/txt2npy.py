import numpy as np
from glob import glob

flist = glob('asd*.txt')

import matplotlib.pyplot as plt
plt.subplot(2,2,1)

for fil in flist:
    data = np.loadtxt(fil)
    np.save(fil.split('.txt')[0], data.T)
    data = np.load(fil.split('.txt')[0] + '.npy')
    plt.plot(data[0,:], data[1,:], label=fil.split('.txt')[0])
    print(np.shape(data))

plt.savefig('test.png', dpi=600)

