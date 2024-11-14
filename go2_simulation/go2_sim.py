import pybullet
import pybullet_data
import rclpy
from rclpy.node import Node
from unitree_go.msg import LowState, LowCmd
import time
from example_robot_data import getModelPath
import os


class Go2Simulator(Node):
    def __init__(self):
        super().__init__('go2_simulation')

        ########################### State
        self.publisher_state = self.create_publisher(LowState, "/lowstate", 10)

        # Timer to publish periodically
        self.period = 1./500  # seconds
        self.timer = self.create_timer(self.period, self.update)

        ########################## Cmd
        self.create_subscription(LowCmd, "/lowcmd", self.receive_cmd_cb, 10)

        robot_subpath = "go2_description/urdf/go2.urdf"
        self.robot_path = os.path.join(getModelPath(robot_subpath), robot_subpath)
        self.robot = 0
        self.init_pybullet()
        self.last_cmd_msg = LowCmd()

    def init_pybullet(self):
        cid = pybullet.connect(pybullet.SHARED_MEMORY)
        self.get_logger().info(f"go2_simulator::pybullet:: cid={cid} ")
        if (cid < 0):
            pybullet.connect(pybullet.GUI, options="--opengl2")
        else:
            pybullet.connect(pybullet.GUI)

        self.get_logger().info(f"go2_simulator::loading urdf : {self.robot_path}")
        self.robot = pybullet.loadURDF(self.robot_path, [0, 0, 0.45])
        pybullet.setGravity(0, 0, -9.81)

        # Load plane and robot
        pybullet.setAdditionalSearchPath(pybullet_data.getDataPath())
        self.plane_id = pybullet.loadURDF("plane.urdf")
        pybullet.resetBasePositionAndOrientation(self.plane_id, [0, 0, 0], [0, 0, 0, 1])

        pybullet.setTimeStep(self.period)

        self.joint_order = ["FR_hip_joint", "FR_thigh_joint", "FR_calf_joint", "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint", "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint", "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint"]

        self.j_idx = []
        for j in self.joint_order:
            self.j_idx.append(self.get_joint_id(j))

        # Somehow this disable joint friction
        pybullet.setJointMotorControlArray(
            bodyIndex=self.robot,
            jointIndices=self.j_idx,
            controlMode=pybullet.VELOCITY_CONTROL,
            targetVelocities=[0. for i in range(12)],
            forces=[0. for i in range(12)],
        )

    def update(self):
        state_msg = LowState()

        # Read sensors
        joint_states = pybullet.getJointStates(self.robot, self.j_idx)
        for joint_idx, joint_state in enumerate(joint_states):
            state_msg.motor_state[joint_idx].mode = 1
            state_msg.motor_state[joint_idx].q = joint_state[0]
            state_msg.motor_state[joint_idx].dq = joint_state[1]

        # Set actuation
        pybullet.setJointMotorControlArray(
            bodyIndex=self.robot,
            jointIndices=self.j_idx,
            controlMode=pybullet.TORQUE_CONTROL,
            forces=[self.last_cmd_msg.motor_cmd[i].tau for i in range(12)]
        )

        # Read IMU
        position, orientation = pybullet.getBasePositionAndOrientation(self.robot)
        state_msg.imu_state.quaternion = orientation
        self.publisher_state.publish(state_msg)

        # Advance simulation by one step
        pybullet.stepSimulation()

    def receive_cmd_cb(self, msg):
        self.last_cmd_msg = msg

    def get_joint_id(self, joint_name):
        num_joints = pybullet.getNumJoints(self.robot)
        for i in range(num_joints):
            joint_info = pybullet.getJointInfo(self.robot, i)
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

