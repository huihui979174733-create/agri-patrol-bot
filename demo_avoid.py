import os
import math
import time
from threading import Thread
from robot import WheeltecRobot
from GPIO_Utilities import UltrasonicRadar, FanController
# ============================================================
# 巡检参数配置区 (方便调试)
# ============================================================
# 速度参数
NORMAL_SPEED = 250      # 正常行驶速度 (mm/s) 建议值
MAX_SPEED = 550         # 极速 (mm/s) 履带底盘上限
ROTATE_SPEED = 0.8      # 旋转角速度 (rad/s), 约45.8度/秒

# 时间参数 (单位：秒)
TIME_STRAIGHT_A = 6.3   # [A] 往返直行单次时间
TIME_WAIT_B = 2.0       # [B] 回到原点后的等待时间
TIME_STRAIGHT_C = 2.2   # [C] 避障前的直行时间
TIME_STRAIGHT_D = 1.8   # [D] 避障绕行时的斜向直行时间
TIME_STRAIGHT_E = 3   # [E] 避障完成后的直行时间

# 避障参数
AVOID_ANGLE = math.pi / 4  # 避障转向角度 45度

# 其他配置
NOTICE_AUDIO = "notice.mp3"
SERIAL_PORT = '/dev/ttyACM0'

# 初始化机器人 (履带底盘)
robot = WheeltecRobot(port=SERIAL_PORT, chassis_type='tracked')


def robot_inspection():
    """履带底盘自动巡检任务主函数"""
    print("\n" + "=" * 60)
    print("[Inspection] 任务启动 | 底盘：履带 | 速度：{}mm/s".format(NORMAL_SPEED))
    print("=" * 60 + "\n")
    
    # 连接机器人
    if not robot.connect():
        print("[Error] 无法连接机器人，请检查串口")
        return
    
    try:
        # 启动数据接收线程 (获取电池、速度等状态)
        robot.start_receive()
        time.sleep(0.5)  # 等待数据稳定
        
        # ========================================================
        # 阶段1: 往返直行测试 (验证基础运动)
        # ========================================================
        print("[Phase 1] 往返直行测试")
        
        # 1.1 向前直行 时间A
        print("  [-] 向前直行 {}s @ {}mm/s".format(TIME_STRAIGHT_A, NORMAL_SPEED))
        robot.move_forward(speed=NORMAL_SPEED)
        time.sleep(TIME_STRAIGHT_A)
        robot.stop()
        time.sleep(0.3)  # 缓冲时间，确保完全停止
        
        # 1.2 原地调头 180度 (pi rad)
        print("  [-] 原地左转调头 180度")
        turn_time = math.pi / ROTATE_SPEED + 0.2# 时间 = 角度/角速度 + 修正值
        robot.rotate_left(speed=ROTATE_SPEED)
        time.sleep(turn_time)
        robot.stop()
        time.sleep(0.3)
        
        # 1.3 再次直行 时间A (方向相反，实际返回原点)
        print("  [-] 向前直行 {}s (返回原点)".format(TIME_STRAIGHT_A))
        robot.move_forward(speed=NORMAL_SPEED)
        time.sleep(TIME_STRAIGHT_A)
        robot.stop()
        time.sleep(0.3)
        
        # 1.4 再次调头 180度 (恢复原始朝向)
        print("  [-] 原地左转调头 180度 (恢复朝向)")
        robot.rotate_left(speed=ROTATE_SPEED)
        time.sleep(turn_time)
        robot.stop()
        time.sleep(0.5)
        
        print("  [-] 倒车测试")
        robot.move_backward(speed=NORMAL_SPEED/2)
        radar = UltrasonicRadar()
        radar_thread = Thread(target=radar.run, kwargs={'duration': 4})
        radar_thread.start()
        for _ in range(4):
            dist = radar.get_distance()
            if dist is not None:
                print(f"  -> 当前距离：{dist:.2f} cm")
                if dist < 15:
                    print("  -> 距离过近，停止倒车")
                    robot.stop()
                elif dist < 25:
                    print("  -> 距离较近，减速")
                    factor = (dist - 10) / 10.0  # 10-20cm线性减速
                    speed = max(NORMAL_SPEED/5, NORMAL_SPEED/2 * factor)  # 最低减速到1/5速度
                    robot.move_backward(speed=speed)
            else:
                print("  -> 等待数据...")
            time.sleep(1)
        
        
        # ========================================================
        # 阶段2: 定点等待
        # ========================================================
        print("\n[Phase 2] 原点等待 {}s".format(TIME_WAIT_B))
        _wait_with_status(TIME_WAIT_B)
        
        # ========================================================
        # 阶段3: 避障前直行
        # ========================================================
        print("\n[Phase 3] 避障前直行 {}s".format(TIME_STRAIGHT_C))
        robot.move_forward(speed=NORMAL_SPEED)
        time.sleep(TIME_STRAIGHT_C)
        robot.stop()
        time.sleep(0.3)
        
        # ========================================================
        # 阶段4: 模拟避障流程 (履带底盘特殊处理)
        # ========================================================
        print("\n[Phase 4] 执行避障流程 (履带模式)")
        print("  [Note] 履带底盘不支持横向平移，采用'转向+直行'模拟斜向避障")
        
        # 4.1 向左转45度 (准备向左前方行驶)
        print("  [-] 左转 {:.0f}度 准备避障".format(math.degrees(AVOID_ANGLE)))
        robot.rotate_left(speed=ROTATE_SPEED)
        time.sleep(AVOID_ANGLE / ROTATE_SPEED)
        robot.stop()
        time.sleep(0.2)
        
        # 4.2 向左前方直行 时间D
        print("  [-] 向左前方直行 {}s".format(TIME_STRAIGHT_D))
        robot.move_forward(speed=NORMAL_SPEED)
        time.sleep(TIME_STRAIGHT_D)
        robot.stop()
        time.sleep(0.2)
        
        # 4.3 向右转45度 (回到原行驶方向)
        print("  [-] 右转 {:.0f}度 回到原路线".format(math.degrees(AVOID_ANGLE)))
        robot.rotate_right(speed=ROTATE_SPEED)
        time.sleep(AVOID_ANGLE / ROTATE_SPEED * 2)
        robot.stop()
        time.sleep(0.3)
        
        # 4.4 [可选] 补偿直行: 确保完全回到原路线
        # 由于履带转向存在滑移误差，可根据实际测试添加微小补偿
        robot.move_forward(speed=50)
        time.sleep(0.5)
        robot.stop()
        
        # ========================================================
        # 阶段5: 避障后直行
        # ========================================================
        print("\n[Phase 5] 避障后直行 {}s".format(TIME_STRAIGHT_E))
        robot.move_forward(speed=NORMAL_SPEED)
        time.sleep(TIME_STRAIGHT_E)
        robot.stop()
        time.sleep(0.3)
        
        # ========================================================
        # 阶段6: 结束动作
        # ========================================================
        print("\n[Phase 6] 任务收尾")
        
        # 6.1 向左侧45度转向
        print("  [-] 左转 {:.0f}度 结束姿态".format(math.degrees(AVOID_ANGLE)))
        robot.rotate_left(speed=ROTATE_SPEED)
        time.sleep(AVOID_ANGLE / ROTATE_SPEED)
        robot.stop()
        time.sleep(0.3)
        
        # 6.2 打印完成信息
        status = robot.get_status()
        print("\n" + "=" * 60)
        print("[Success] 巡检任务圆满完成")
        print("  [Status] 最终状态:")
        print("    - 电池电压: {:.2f}V".format(status.battery_voltage))
        print("    - 底盘朝向: 右偏45度")
        print("    - 行驶速度: {}mm/s (设定值)".format(NORMAL_SPEED))
        print("=" * 60 + "\n")
        
        
        print("[Inspection] 任务流程执行完毕")
        
    except KeyboardInterrupt:
        print("\n[Warning] 用户中断，执行紧急停止")
        robot.stop()
    except Exception as e:
        print("\n[Error] 执行异常: {}: {}".format(type(e).__name__, e))
        robot.stop()
        import traceback
        traceback.print_exc()
    finally:
        # 清理资源
        robot.stop_receive()
        robot.disconnect()
        print("[Info] 机器人连接已断开")


def _wait_with_status(duration: float):
    """带状态显示的等待函数"""
    start = time.time()
    while time.time() - start < duration:
        elapsed = time.time() - start
        status = robot.get_status()
        print("\r  [Waiting] 等待中... {:.1f}/{:.1f}s | 电压: {:.2f}V".format(
            elapsed, duration, status.battery_voltage), end='', flush=True)
        time.sleep(0.5)
    print()  # 换行


if __name__ == '__main__':
    print("=" * 60)
    print("农业巡检智能服务应用 - 树莓派后端")
    print("=" * 60)
    
    try:
        print("[Action] 执行巡检任务...")
        robot_inspection()
        print("-" * 60)

    except KeyboardInterrupt:
        print("\n[Warning] 检测到 Ctrl+C，正在关闭服务...")
        robot.stop()
    finally:
        robot.disconnect()
        print("[Server] 服务已安全停止")