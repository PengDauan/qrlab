from _HP_8657 import HP_8657

class HP_8657B(HP_8657):

    def  __init__(self, name, address, reset=False, freq=1e6, pow=None):
        HP_8657.__init__(self, name, address, '8657B', freq=freq, pow=pow)
