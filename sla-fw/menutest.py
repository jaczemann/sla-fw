import pydbus

a = pydbus.SystemBus().get("cz.prusa3d.sl1.admin0")
a.enter()
for i in a.children:
	print(i)
