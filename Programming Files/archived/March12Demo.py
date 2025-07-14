import opticalmodule
import time

if __name__ == "__main__":
	module = opticalmodule.OpticalModule()
	module.add_sample('sample1', 14, 0.5)
	module.currSample.set_bounding_box([(125,105),(125,75),(95,105),(95,75)])
	module.home_all()
	module.go_to(x=110,y=90)
	print(module.auto_focus(75,80,0.05))
	module.random_sampling(6,True)
	
	
	#while True:
	#	state = module.limitSwitchY.is_pressed()
		
		#print(state)
	#	time.sleep(1)
	
