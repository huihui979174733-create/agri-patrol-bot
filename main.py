from threading import Thread
from app import app, camera_manager,dev_info
from robot import WheeltecRobot, RobotStatus, list_serial_ports

robot = WheeltecRobot()

def robot_inspection():
    
    pass


if __name__ == '__main__':
    print("=" * 50)
    print("农业巡检智能服务应用 - 树莓派4B+ 后端")
    print("=" * 50)
    
    # 启动摄像头
    print("\n正在启动摄像头...")
    if camera_manager.start():
        print("✓ 摄像头启动成功\n")
    else:
        print("✗ 摄像头启动失败，视频流将不可用\n")
    
    # 启动Flask服务器
    print("启动Flask服务器...")
    print("访问地址: http://<树莓派IP>:5000")
    print("按Ctrl+C停止服务器\n")
    
    try:
        # 在树莓派上运行，监听所有接口
        app_thread = Thread(target=app.run, kwargs={
            'host': '0.0.0.0',
            'port': 5000,
            'debug': False
        },daemon=True)
        app_thread.start()
        
        while app_thread.is_alive():
            print(f"当前指令: {dev_info.current_cmd} | CPU使用率: {dev_info.cpu_usage}% | 内存使用率: {dev_info.memory_usage}% | 温度: {dev_info.cpu_temperature}°C")
            if dev_info.current_cmd == "start_inspection":
                print("正在执行巡检任务...")
                robot_inspection()
            elif dev_info.current_cmd == "stop_inspection":
                print("巡检任务已停止")
            elif dev_info.current_cmd == "capture_image":
                print("正在捕获图像...")
            else:
                print("设备处于空闲状态")
            print("-" * 50)
            app_thread.join(timeout=1)

        # app.run(
        #     host='0.0.0.0',  # 允许外部访问
        #     port=5000,
        #     debug=False,  # 生产环境关闭debug
        #     threaded=True  # 启用多线程
        # )
    except KeyboardInterrupt:
        app_thread.join()
        print("\n正在关闭服务器...")
    finally:
        camera_manager.stop()
        print("服务器已停止")
        
