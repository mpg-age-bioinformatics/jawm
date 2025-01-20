#!/usr/bin/env python3
import time
print("Hello from {{APPNAME}}")
print("4 + 3 =", 4 + 3)
print("start sleeping!")
time.sleep(15)
print("Print some fruits name:")
for fruit in {{FRUITLIST}}:
    print(f"Fruit: {fruit}")
print("{{BYEMSG}}")
