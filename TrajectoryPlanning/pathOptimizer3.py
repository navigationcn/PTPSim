"""
MIT License

Copyright (c) 2019 ming

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
===============================
@File  : pathOptimizer3.py
@Author: ming.ustb@outlook.com
@Date  : 19-6-11
@GitHub: https://github.com/yangmingustb/PTPSim
"""


from casadi import *
import numpy as np
import math
import matplotlib.pyplot as plt
import model.simModel as car
import Curves.cubic_spline as cubicSpline
import FrenetMath.FrenetToCartesian as ftc
import FrenetMath.kappaCalculate as calKappa
import FrenetMath.calHeading as heading
import TrajectoryPlanning.SpeedProfileOptimizer3 as speed
import TrajectoryPlanning.pathPlanner3 as pathPlanner


show_animation = True
show_obstacle = True
show_vehicle_animation = False
showRefinedPath = True
showRoughPath = True
showVehicleStart = True
showRoughKappa=True
showRefinedKappa=True

s_max = 100.0
reso_s = 1.0
n_s = int(s_max / reso_s)
r_circle = 1.0  # 车体包络圆
d_circle = 2.0  # 圆心间距
obs_inflation = 1.5
safe_distance = obs_inflation + r_circle
kappa_max = 0.187
w_d = 1.0
w_dd = 10.0
w_ddd = 50.0
w_ref = 0.1

lane_width = 3.75
refLineRho = lane_width*0.5
laneChaneRefLine = lane_width*1.5
rho_r = [laneChaneRefLine for i in range(n_s + 3)]
for i in range(20):
	rho_r[i] = refLineRho
rho_max = lane_width*2  # 行驶通道的左右边界
rho_min = 0.0+r_circle
# 初值
rho_init_guess = laneChaneRefLine * np.ones((1, n_s + 3))

obstacleHeading=0.0 * math.pi / 180.0

# 起点状态
s0 = 100.0
start_SRho = [s0, refLineRho, 0.0 * math.pi / 180.0]
kappa0 = -0.01
# 里程s的序列
s = [i for i in np.arange(s0 + reso_s, (s0+s_max + 4 * reso_s), reso_s)]
print("len(s)", len(s))

# 障碍物表示
static_obs = [[s0+20, refLineRho-0.3], [s0+40, refLineRho+0.5], [s0+70, refLineRho-0.2]]
rho_min_list = [rho_min for i in range(n_s+3)]
rho_max_list = [rho_max for i in range(n_s+3)]


def boundValue(efficients):
	# 等式约束
	# 注意，这里生成的坐标位置是最右侧车道线的，不是参考线的
	xr0, yr0, thetar0 = ftc.search_in_coefficients(s0, efficients)
	s1 = s0 + reso_s
	# xr1, yr1, thetar1 = ftc.search_in_coefficients(s1, efficients)
	s2 = s0 + 2 * reso_s
	xr2, yr2, thetar2 = ftc.frenetToXY(s2, refLineRho, 0, efficients)

	x0, y0, theta0 = ftc.frenetToXY(start_SRho[0], start_SRho[1], start_SRho[2], efficients)
	print("x0, y0, theta0:", x0, y0, theta0)
	rho_1 = reso_s * (math.tan(theta0 - thetar0)) + start_SRho[1]
	x1, y1, theta1 = ftc.frenetToXY(s1, rho_1, 0, efficients)
	print("x1, y1, theta1:", x1, y1, theta1)

	m = kappa0 * ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** (3 / 2)
	n = (x1 - x0) * (yr2 - 2 * y1 + y0) + (y1 - y0) * (xr2 - 2 * x1 + x0)
	q = (x1 - x0) * math.sin(thetar2 + math.pi / 2.0) - (y1 - y0) * math.cos(thetar2 + math.pi / 2.0)
	rho_2 = (m - n) / q    # 本来求出的是到参考线的距离
	# 加上参考线到最右侧车道线的距离，是真正的偏移量，
	# 这个问题debug了很久，一定要将方程设在参考线处，可以免去很多麻烦
	rho_2 = rho_2 + refLineRho
	print("rho1, rho2:", rho_1, rho_2)
	return rho_1, rho_2


# Objective
def objective(rho):
	f_d = 0
	f_dd = 0
	f_ddd = 0
	f_ref = 0
	for i in range(n_s):
		f_d = f_d + (rho[i + 1] - rho[i]) ** 2 / (reso_s ** 2)
		f_dd = f_dd + (rho[i + 2] - 2 * rho[i + 1] + rho[i]) ** 2 / (reso_s ** 4)
		f_ddd = f_ddd + (rho[i + 3] - 3 * rho[i + 2] + 3 * rho[i + 1] - rho[i]) ** 2 / reso_s ** 6
		f_ref = f_ref + (rho[i] - rho_r[i]) ** 2

	# print('=========================================')
	# print(f_d)
	# print(f_dd)
	# print(f_ddd)
	# print(f_ref)

	f_d = reso_s * w_d * f_d
	f_dd = reso_s * w_dd * f_dd
	f_ddd = reso_s * w_ddd * f_ddd
	f_ref = reso_s * w_ref * f_ref
	f = f_d + f_dd + f_ddd + f_ref
	return f


def inequality_cons(rho, s, optimization, efficients):
	# 曲率约束
	for i in range(n_s):
		x0, y0, theta0 = ftc.frenetToXY(s[i], rho[i], 0, efficients)
		x1, y1, theta1 = ftc.frenetToXY(s[i + 1], rho[i + 1], 0, efficients)
		x2, y2, theta2 = ftc.frenetToXY(s[i + 2], rho[i + 2], 0, efficients)

		k1 = (x1 - x0) * (y2 - 2 * y1 + y0)
		k2 = (y1 - y0) * (x2 - 2 * x1 + x0)
		k3 = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** (3.0 / 2.0)
		kappa1 = -k1 + k2 + k3 * kappa_max
		kappa2 = k1 - k2 + k3 * kappa_max
		optimization.subject_to(kappa1 >= 0)
		optimization.subject_to(kappa2 >= 0)

	# 障碍物约束
	for i in range(n_s + 3):
		# the first obs
		if ((s[i] - static_obs[0][0]) ** 2 < 9):

			c1_obs = (s[i] - static_obs[0][0]) ** 2 + (rho[i] - static_obs[0][1]) ** 2
			c2_obs = (s[i] + d_circle - static_obs[0][0]) ** 2 + (rho[i] - static_obs[0][1]) ** 2
			c3_obs = (s[i] + 2 * d_circle - static_obs[0][0]) ** 2 + (rho[i] - static_obs[0][1]) ** 2
			optimization.subject_to(c1_obs >= safe_distance ** 2)
			optimization.subject_to(c2_obs >= safe_distance ** 2)
			optimization.subject_to(c3_obs >= safe_distance ** 2)
		# the second obs
		if ((s[i] - static_obs[1][0]) ** 2 < 9):
			c1_obs2 = (s[i] - static_obs[1][0]) ** 2 + (rho[i] - static_obs[1][1]) ** 2
			c2_obs2 = (s[i] + d_circle - static_obs[1][0]) ** 2 + (rho[i] - static_obs[1][1]) ** 2
			c3_obs2 = (s[i] + 2 * d_circle - static_obs[1][0]) ** 2 + (rho[i] - static_obs[1][1]) ** 2

			optimization.subject_to(c1_obs2 >= safe_distance ** 2)
			optimization.subject_to(c2_obs2 >= safe_distance ** 2)
			optimization.subject_to(c3_obs2 >= safe_distance ** 2)

		# the second obs
		if ((s[i] - static_obs[2][0]) ** 2 < 9):
			c1_obs3 = (s[i] - static_obs[2][0]) ** 2 + (rho[i] - static_obs[2][1]) ** 2
			c2_obs3 = (s[i] + d_circle - static_obs[2][0]) ** 2 + (rho[i] - static_obs[2][1]) ** 2
			c3_obs3 = (s[i] + 2 * d_circle - static_obs[2][0]) ** 2 + (rho[i] - static_obs[2][1]) ** 2

			optimization.subject_to(c1_obs3 >= safe_distance ** 2)
			optimization.subject_to(c2_obs3 >= safe_distance ** 2)
			optimization.subject_to(c3_obs3 >= safe_distance ** 2)


def allConstraints(rho, s, optimization, efficients):
	# 曲率和避障约束
	inequality_cons(rho, s, optimization, efficients)
	rho1, rho2 = boundValue(efficients)
	# 边值条件约束
	optimization.subject_to(rho[0] == rho1)
	optimization.subject_to(rho[1] == rho2)

	# 取值范围约束
	optimization.subject_to(optimization.bounded(rho_min_list, rho, rho_max_list))
	return None


def ipoptSolver(efficients):
	# construct a optimization problem
	optimization = casadi.Opti()

	# column vector, decision variables
	rho = optimization.variable(n_s + 3)  # number of variables:n_s+3
	# print("rho_shape[0]:", rho.shape[0])

	f = objective(rho)
	optimization.minimize(f)

	allConstraints(rho, s, optimization, efficients)

	p_opts = {"expand": True}
	s_opts = {"max_iter": 100}
	optimization.solver("ipopt", p_opts, s_opts)
	# 设置初值
	rho1, rho2 = boundValue(efficients)
	rho_init_guess[0][0]=rho1
	rho_init_guess[0][1]=rho2
	optimization.set_initial(rho, rho_init_guess)
	solution = optimization.solve()
	rho_vector = solution.value(rho)
	# print("rho_vector:", rho_vector)
	return  rho_vector


def ToMPC():
	efficients = cubicSpline.saveEfficients()
	rho_vector = ipoptSolver(efficients)
	theta_rho = []
	for i in range(len(s) - 1):
		state0 = [s[i], rho_vector[i]]
		state1 = [s[i + 1], rho_vector[i + 1]]
		tmp_theta = heading.calHeadingFrenet(state0, state1)
		theta_rho.append(tmp_theta)
	theta_rho.append(theta_rho[-1])

	x = []
	y = []
	theta = []
	# print(s)
	for j in range(len(s)):
		tmpX, tmpY, tmpTheta = ftc.frenetToXY(s[j], rho_vector[j], theta_rho[j], efficients)
		x.append(tmpX)
		y.append(tmpY)
		theta.append(tmpTheta)
	kappa_list = calKappa.path_kappa(rho_vector, s, efficients)
	return x[0:n_s+1], y[0:n_s+1], theta[0:n_s+1], kappa_list


def plotGraph():
	# plot graph
	plt.figure(figsize=(3.5, 3.5 * 0.62))  # 单位英寸， 3.5
	font1 = {'family': 'Times New Roman', 'weight': 'normal', 'size': 10}
	plt.rcParams['font.sans-serif'] = ['Times New Roman']  # 如果要显示中文字体，则在此处设为：SimHei

	p1 = [0.2, 0.2, 0.7, 0.7]
	plt.axes(p1)

	efficients = cubicSpline.saveEfficients()
	rho_vector = ipoptSolver(efficients)
	theta_rho = []
	for i in range(len(s)-1):
		state0 = [s[i], rho_vector[i]]
		state1 = [s[i + 1], rho_vector[i + 1]]
		tmp_theta = heading.calHeadingFrenet(state0, state1)
		theta_rho.append(tmp_theta)
	theta_rho.append(theta_rho[-1])

	x = []
	y = []
	theta = []
	# print(s)
	for j in range(len(s)):
		tmpX, tmpY, tmpTheta = ftc.frenetToXY(s[j], rho_vector[j], theta_rho[j], efficients)
		x.append(tmpX)
		y.append(tmpY)
		theta.append(tmpTheta)

	tmp_s = []
	tmp_rho = []
	tmp_thetaRho = []
	if showRoughPath:
		tmp_s, tmp_rho, tmp_thetaRho = pathPlanner.ToPathOptimizer3(efficients)

	if showRefinedPath:
		plt.plot(x, y, c='cyan', linewidth=0.6, alpha=1, label='Refined path')
	if showVehicleStart:
		tmpx, tmpy, tmptheta = ftc.frenetToXY(start_SRho[0], start_SRho[1], obstacleHeading, efficients)
		car.simVehicle([tmpx, tmpy], tmptheta, 'b', 0.8)
	# print(len(x), len(y), len(theta))
	# print(x[0], y[0], theta[0])

	# plot obstacles
	# if show_obstacle:
	# 	c=['r', 'gold', 'darkorange']
	# 	for i in range(len(dyn_obs)):
	# 		obs_s = [j for j in np.arange(dyn_obs[-(i+1)][0], dyn_obs[-(i+1)][0]+ 50, 1)]
	# 		obs_rho = [dyn_obs[-(i+1)][1] for q in np.arange(dyn_obs[-(i+1)][0], dyn_obs[-(i+1)][0]+ 50, 1)]
	# 		for m in range(0, len(obs_s), 1):
	# 			time_stamp = m / len(obs_s) + 0.08
	# 			if time_stamp > 1.0:
	# 				time_stamp = 1.0
	# 			tmpx, tmpy, tmptheta = ftc.frenetToXY(obs_s[m], obs_rho[m], obstacleHeading, efficients)
	# 			car.simVehicle([tmpx, tmpy], tmptheta, c[i], time_stamp)

	if show_obstacle:
		c=['r', 'gold', 'darkorange']
		for i in range(len(static_obs)):
			tmpx, tmpy, tmptheta = ftc.frenetToXY(static_obs[-(i+1)][0], static_obs[-(i+1)][1], obstacleHeading, efficients)
			car.simVehicle([tmpx, tmpy], tmptheta, c[i], 0.8)

	if show_vehicle_animation:
		for i in range(0, n_s, 2):
			time_stamp = i / n_s +0.1
			if time_stamp > 1.0:
				time_stamp=1.0
			car.simVehicle([x[i], y[i]], theta[i], 'b', time_stamp)
			# plt.pause(0.001)

	plt.grid(linestyle="--", linewidth=0.5, alpha=1)
	# plt.title('x-y Graph', font1)
	plt.xlabel('x (m)', font1)
	plt.ylabel('y (m)', font1)
	plt.xticks(fontproperties='Times New Roman', fontsize=10)
	plt.yticks(fontproperties='Times New Roman', fontsize=10)
	# plt.legend(loc=0)  # 图例位置自动
	plt.xlim(30, 140)
	plt.ylim(80, 130)
	# plt.axis('equal')
	plt.savefig('../SimGraph/pathOptimization3Path060404.svg')
	plt.savefig('../SimGraph/pathOptimization3Path060404.tiff', dpi=600)

	plt.figure(figsize=(3.5, 1.8))  # 单位英寸， 3.5
	font1 = {'family': 'Times New Roman', 'weight': 'normal', 'size': 10}
	plt.rcParams['font.sans-serif'] = ['Times New Roman']  # 如果要显示中文字体，则在此处设为：SimHei

	p2 = [0.2, 0.25, 0.7, 0.6]
	plt.axes(p2)
	if showRoughKappa:
		rough_kappa = calKappa.path_kappa(tmp_rho, tmp_s, efficients)
		print("--------------")
		print(len(rough_kappa))
		plt.plot(tmp_s[0:-2], rough_kappa, c= 'magenta', linestyle="-", linewidth=0.5, alpha=1,label='Rough Path Curvature Profile')

	if showRefinedKappa:
		kappa_list = calKappa.path_kappa(rho_vector, s, efficients)
		plt.plot(s[0:n_s + 1], kappa_list, c= 'cyan', linestyle="-", linewidth=0.5, alpha=1, label='Refined Path Curvature Profile')

		y = [max(kappa_list) for i in range(n_s + 1)]
		y2 = [min(kappa_list) for i in range(n_s + 1)]
		plt.plot(s[0:n_s + 1], y, c= 'k', linestyle="--", linewidth=0.5, alpha=1)
		plt.plot(s[0:n_s + 1], y2, c= 'k', linestyle="--", linewidth=0.5, alpha=1)
		plt.title('Curvature Profile', font1)
		plt.grid(linestyle="--", linewidth=0.5, alpha=1)
		plt.xlabel('s (m)', font1)
		plt.ylabel('kappa (1/m)', font1)
		plt.xlim(90, 210)
		plt.ylim(-0.1, 0.3)
		plt.legend(loc=0)  # 图例位置自动
		plt.savefig('../SimGraph/pathOptimization3Kappa060404.svg')
		plt.savefig('../SimGraph/pathOptimization3Kappa060404.tiff', dpi=600)
		plt.show()


if __name__ == '__main__':
	plotGraph()
