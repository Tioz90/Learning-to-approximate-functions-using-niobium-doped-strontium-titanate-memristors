import numpy as np


class MemristorLearningRule:
    def __init__( self, learning_rate, dt=0.001 ):
        self.learning_rate = learning_rate
        self.dt = dt
        
        # only used in supervised rules (ex. mPES)
        self.last_error = None
        
        self.input_size = None
        self.output_size = None
        
        self.weights = None
        self.memristors = None
        self.logging = None
    
    def get_error_signal( self ):
        return self.last_error
    
    def find_spikes( self, input_activities, output_activities=None ):
        spiked_pre = np.tile(
                np.array( np.rint( input_activities ), dtype=bool ), (self.output_size, 1)
                )
        spiked_post = np.tile(
                np.expand_dims(
                        np.array( np.rint( output_activities ), dtype=bool ), axis=1 ), (1, self.input_size)
                ) if output_activities is not None else np.ones( (1, self.input_size) )
        
        return np.logical_and( spiked_pre, spiked_post )


class mHopfieldHebbian( MemristorLearningRule ):
    def __init__( self, learning_rate=1e-6, dt=0.001, beta=1.0 ):
        super().__init__( learning_rate, dt )
        
        self.alpha = self.learning_rate * self.dt
        self.has_learning_signal = True
    
    def __call__( self, t, x ):
        input_activities = x
        
        spiked_map = self.find_spikes( input_activities, input_activities )
        
        if spiked_map.any():
            for j, i in np.transpose( np.where( spiked_map ) ):
                # ignore diagonal
                if i != j:
                    self.weights[ j, i ] = self.memristors[ j, i ].pulse( spiked_map[ j, i ],
                                                                          value="conductance",
                                                                          method="same"
                                                                          )
                    # symmetric update
                    # could also route memristor [j,i] to weight [i,j] like in the paper
                    self.weights[ i, j ] = self.memristors[ i, j ].pulse( spiked_map[ i, j ],
                                                                          value="conductance",
                                                                          method="same"
                                                                          )
        
        # calculate the output at this timestep
        return np.dot( self.weights, input_activities )


class mOja( MemristorLearningRule ):
    def __init__( self, learning_rate=1e-6, dt=0.001, beta=1.0 ):
        super().__init__( learning_rate, dt )
        
        self.alpha = self.learning_rate * self.dt
        self.beta = beta
        self.has_learning_signal = False
    
    def __call__( self, t, x ):
        input_activities = x[ :self.input_size ]
        output_activities = x[ self.input_size:self.input_size + self.output_size ]
        
        post_squared = self.alpha * output_activities * output_activities
        forgetting = -self.beta * self.weights * np.expand_dims( post_squared, axis=1 )
        hebbian = np.outer( self.alpha * output_activities, input_activities )
        update_direction = hebbian - forgetting
        
        # squash spikes to False (0) or True (100/1000 ...) or everything is always adjusted
        spiked_map = self.find_spikes( input_activities, output_activities )
        
        # we only need to update the weights for the neurons that spiked so we filter
        if spiked_map.any():
            for j, i in np.transpose( np.where( spiked_map ) ):
                self.weights[ j, i ] = self.memristors[ j, i ].pulse( update_direction[ j, i ],
                                                                      value="conductance",
                                                                      method="same"
                                                                      )
        
        # calculate the output at this timestep
        return np.dot( self.weights, input_activities )


class mBCM( MemristorLearningRule ):
    def __init__( self, learning_rate=1e-9, dt=0.001 ):
        super().__init__( learning_rate, dt )
        
        self.alpha = self.learning_rate * self.dt
        self.has_learning_signal = False
    
    def __call__( self, t, x ):
        
        input_activities = x[ :self.input_size ]
        output_activities = x[ self.input_size:self.input_size + self.output_size ]
        theta = x[ self.input_size + self.output_size: ]
        
        update_direction = output_activities - theta
        # function \phi( a, \theta ) that is the moving threshold
        update = self.alpha * output_activities * update_direction
        
        # squash spikes to False (0) or True (100/1000 ...) or everything is always adjusted
        spiked_map = self.find_spikes( input_activities, output_activities )
        
        # we only need to update the weights for the neurons that spiked so we filter
        if spiked_map.any():
            for j, i in np.transpose( np.where( spiked_map ) ):
                self.weights[ j, i ] = self.memristors[ j, i ].pulse( update_direction[ j ],
                                                                      value="conductance",
                                                                      method="same"
                                                                      )
        
        # calculate the output at this timestep
        return np.dot( self.weights, input_activities )


class mPES( MemristorLearningRule ):
    def __init__( self, encoders, learning_rate=1e-5, dt=0.001 ):
        super().__init__( learning_rate, dt )
        
        self.encoders = encoders
        # TODO mettere a True?
        self.has_learning_signal = False
        
        # TODO can I remove the inverse method from pulse?
    
    def __call__( self, t, x ):
        input_activities = x[ :self.input_size ]
        # squash error to zero under a certain threshold or learning rule keeps running indefinitely
        error = x[ self.input_size: ] if abs( x[ self.input_size: ] ) > 10**-5 else 0
        alpha = self.learning_rate * self.dt / self.input_size
        self.last_error = error
        
        # we are adjusting weights so calculate local error
        local_error = alpha * np.dot( self.encoders, error )
        
        # squash spikes to False (0) or True (100/1000 ...) or everything is always adjusted
        spiked_map = self.find_spikes( input_activities )
        
        # we only need to update the weights for the neurons that spiked so we filter for their columns
        if spiked_map.any():
            for j, i in np.transpose( np.where( spiked_map ) ):
                self.weights[ j, i ] = self.memristors[ j, i ].pulse( local_error[ j ],
                                                                      value="conductance",
                                                                      method="inverse"
                                                                      )
        
        # calculate the output at this timestep
        return np.dot( self.weights, input_activities )
