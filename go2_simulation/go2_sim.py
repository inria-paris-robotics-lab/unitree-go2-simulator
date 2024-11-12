import pybullet as p
import pybullet_data
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu
from unitree_go.msg import LowState, LowCmd
import logging
import time


class Go2Simulator(Node):
    def __init__(self):
        super().__init__('go2_simulation')
    
        ########################### State
        self.state_topic = self.declare_parameter("state_topic_name", "/lowstate").value
        self.publisher_state = self.create_publisher(LowState, self.state_topic, 10)

        # Timer to publish periodically
        timer_period = 0.1  # seconds
        self.timer = self.create_timer(timer_period, self.update_state)
    
        ########################## Cmd      
        self.cmd_topic = self.declare_parameter("cmd_topic_name", "/lowcmd").value
        self.create_subscription(LowCmd, self.cmd_topic, self.apply_cmd, 10)

        self.robot_path = self.declare_parameter("robot_path", "")
        self.robot = 0
        self.init_pybullet()
        self.last_msg = None

    def init_pybullet(self):
        try:
            cid = p.connect(p.SHARED_MEMORY)
            self.get_logger().info(f"go2_simulator::pybullet:: cid={cid} ")
            if (cid < 0):
                p.connect(p.GUI, options="--opengl2")
            else:
                p.connect(p.GUI)
            self.get_logger().info(f"go2_simulator::connect complete")
            p.setAdditionalSearchPath(pybullet_data.getDataPath())
            self.get_logger().info(f"go2_simulator::loading urdf")

            self.robot_path = self.get_parameter("robot_path").get_parameter_value().string_value
            self.get_logger().info(f"go2_simulator::loading urdf : {self.robot_path}")
            self.robot = p.loadURDF(self.robot_path, [0, 0, 0.45])
            p.setGravity(0, 0, -9.81)
            
            # Load plane and robot
            p.setAdditionalSearchPath(pybullet_data.getDataPath())
            self.plane_id = p.loadURDF("plane.urdf")
            p.resetBasePositionAndOrientation(self.plane_id, [0, 0, 0], [0, 0, 0, 1])
            for _ in range(40):
              p.stepSimulation()

            self.joint_order = ["FR_hip_joint", "FR_thigh_joint", "FR_calf_joint", "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint", "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint", "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint"]

            self.j_idx = []
            for j in self.joint_order:
                self.j_idx.append(self.get_joint_id(j))
        
        except:
            logging.exception("error occurred")
            pass

    def update_state(self):
        state_msg = LowState()
        for joint_idx in range(12):
            joint_state = p.getJointState(self.robot, self.j_idx[joint_idx])
            state_msg.motor_state[joint_idx].mode = 1
            state_msg.motor_state[joint_idx].q = joint_state[0]
            state_msg.motor_state[joint_idx].dq = joint_state[1]

        position, orientation = p.getBasePositionAndOrientation(self.robot)
        state_msg.imu_state.quaternion = orientation
        self.publisher_state.publish(state_msg)

    def apply_cmd(self, msg):
        current_msg_time = self.get_clock().now()
        for joint_idx in range(12):
            target_position = msg.motor_cmd[joint_idx].q
            target_velocity = msg.motor_cmd[joint_idx].dq
            j_id = self.j_idx[joint_idx]

            # Set joint control using POSITION_CONTROL, VELOCITY_CONTROL, or TORQUE_CONTROL
            p.setJointMotorControl2(
                bodyIndex=self.robot,
                jointIndex=j_id,
                controlMode=p.POSITION_CONTROL,  
                targetPosition=target_position,
                targetVelocity=target_velocity
            )

        p.stepSimulation()
        time_diff = (current_msg_time - self.last_msg_time).nanoseconds * 1e-9
        time.sleep(time_diff)
    
    def get_joint_id(self, joint_name):
        num_joints = p.getNumJoints(self.robot)
        for i in range(num_joints):
            joint_info = p.getJointInfo(self.robot, i)
            if joint_info[1].decode("utf-8") == joint_name:
                return i
        return None  # Joint name not found
    
def main(args=None):
    rclpy.init(args=args)
    try:
        go2_simulation = Go2Simulator()
        rclpy.spin(go2_simulation)
    except rclpy.exceptions.ROSInterruptException:
        pass

    go2_simulation.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
