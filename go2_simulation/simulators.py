import numpy as np
import pinocchio as pin
import example_robot_data as erd
from go2_simulation.simulation_utils import (
    addFloor,
    removeBVHModelsIfAny,
    setPhysicsProperties,
    Simulation,
    addSystemCollisionPairs
)
import os
import pybullet 
import pybullet_data
from scipy.spatial.transform import Rotation as R
from ament_index_python.packages import get_package_share_directory
import yaml

class SimpleSimulator():
    def __init__(self, timestep):
        ########################## Load robot model and geometry
        robot = erd.load("go2")
        self.rmodel = robot.model
        self.q0 = self.rmodel.referenceConfigurations["standing"]
        self.njoints = self.rmodel.nv - 6

        URDF_SUBPATH = "/go2_description/urdf/go2.urdf"
        package_dir = erd.getModelPath(URDF_SUBPATH)
        file_path = package_dir + URDF_SUBPATH

        with open(file_path, 'r') as file:
            file_content = file.read()

        self.geom_model = pin.GeometryModel()
        pin.buildGeomFromUrdfString(self.rmodel, file_content, pin.GeometryType.VISUAL, self.geom_model, package_dir)

        self.init_simple(timestep)

    def init_simple(self, timestep):
        visual_model = self.geom_model.copy()
        addFloor(self.geom_model, visual_model)

        # Set simulation properties
        args = None
        arg_path = os.path.join(
            get_package_share_directory('go2_simulation'),
            'config',
            'sim_params.yaml'
        )
        with open(arg_path, 'r') as file:
          args = yaml.safe_load(file)

        args["dt"] = timestep
        initial_q = np.array([0, 0, 0.2, 0, 0, 0, 1, 0.0, 1.00, -2.51, 0.0, 1.09, -2.61, 0.2, 1.19, -2.59, -0.2, 1.32, -2.79])
        setPhysicsProperties(self.geom_model, args["material"], args["compliance"])
        removeBVHModelsIfAny(self.geom_model)
        addSystemCollisionPairs(self.rmodel, self.geom_model, initial_q)

         # Remove all pair of collision which does not concern floor collision
        i = 0
        while i < len(self.geom_model.collisionPairs):
            cp = self.geom_model.collisionPairs[i]
            if self.geom_model.geometryObjects[cp.first].name != 'floor' and self.geom_model.geometryObjects[cp.second].name != 'floor':
                self.geom_model.removeCollisionPair(cp)
            else:
                i = i + 1
        
        # Create the simulator object
        self.simulator = Simulation(self.rmodel, self.geom_model, visual_model, initial_q, np.zeros(self.rmodel.nv), args) 
    
    def get_state(self):
        q_current, v_current = self.simulator.get_state()

        return q_current, v_current

    def execute_step(self, tau_des, q_des, v_des, kp_des, kd_des):
        # Get sub step state
        q_current, v_current = self.simulator.get_state()
        tau_cmd = tau_des - np.multiply(q_current[7:]-q_des, kp_des) - np.multiply(v_current[6:]-v_des, kd_des)

        # Set actuation and run one step of simulation
        torque_simu = np.zeros(self.rmodel.nv)
        torque_simu[6:] = tau_cmd
        self.simulator.execute(torque_simu)


class BulletSimulator():
    def __init__(self, timestep):
        ########################## Load robot model and geometry
        robot_subpath = "go2_description/urdf/go2.urdf"
        self.robot_path = os.path.join(erd.getModelPath(robot_subpath), robot_subpath)
        self.robot = 0
        self.init_pybullet(timestep)

    def init_pybullet(self, timestep):
        cid = pybullet.connect(pybullet.SHARED_MEMORY)
        if (cid < 0):
            pybullet.connect(pybullet.GUI, options="--opengl2")
        else:
            pybullet.connect(pybullet.GUI)

        # Load robot
        self.robot = pybullet.loadURDF(self.robot_path, [0, 0, 0.3])

        # Load ground plane
        pybullet.setAdditionalSearchPath(pybullet_data.getDataPath())
        self.plane_id = pybullet.loadURDF("plane.urdf")
        self.localInertiaPos = pybullet.getDynamicsInfo(self.robot, -1)[3]
        pybullet.resetBasePositionAndOrientation(self.plane_id, self.localInertiaPos, [0, 0, 0, 1])

        pybullet.setTimeStep(timestep)

        self.joint_order = ["FR_hip_joint", "FR_thigh_joint", "FR_calf_joint", "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint", "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint", "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint"]
        self.njoints = len(self.joint_order)

        self.j_idx = []
        for j in self.joint_order:
            self.j_idx.append(self.get_joint_id(j))

        # Set robot initial config on the ground
        # initial_q = [0.39, 1.00, -2.51, -0.30, 1.09, -2.61, 0.59, 1.19, -2.59, -0.40, 1.32, -2.79]
        initial_q = [0.0, 1.00, -2.51, 0.0, 1.09, -2.61, 0.2, 1.19, -2.59, -0.2, 1.32, -2.79]
        for i, id in enumerate(self.j_idx):
            pybullet.resetJointState(self.robot, id, initial_q[i])

        # gravity and feet friction
        pybullet.setGravity(0, 0, -9.81)

        # Somehow this disable joint friction
        pybullet.setJointMotorControlArray(
            bodyIndex=self.robot,
            jointIndices=self.j_idx,
            controlMode=pybullet.VELOCITY_CONTROL,
            targetVelocities=[0. for i in range(12)],
            forces=[0. for i in range(12)],
        )
    
    def get_joint_id(self, joint_name):
        num_joints = pybullet.getNumJoints(self.robot)
        for i in range(num_joints):
            joint_info = pybullet.getJointInfo(self.robot, i)
            if joint_info[1].decode("utf-8") == joint_name:
                return i
        return None  # Joint name not found
    
    def get_state(self):
        joint_states = pybullet.getJointStates(self.robot, self.j_idx)
        joint_position = np.array([joint_state[0] for joint_state in joint_states])
        joint_velocity = np.array([joint_state[1] for joint_state in joint_states])
        linear_pose, angular_pose = pybullet.getBasePositionAndOrientation(self.robot)
        linear_vel, angular_vel = pybullet.getBaseVelocity(self.robot)

        rotation = R.from_quat(angular_pose)
        linear_pose -= rotation.as_matrix() @ self.localInertiaPos

        q_current = np.concatenate((np.array(linear_pose), np .array(angular_pose), joint_position))
        v_current = np.concatenate((np.array(linear_vel), np.array(angular_vel), joint_velocity))

        return q_current, v_current

    def execute_step(self, tau_des, q_des, v_des, kp_des, kd_des):
        # Get sub step state
        joint_states = pybullet.getJointStates(self.robot, self.j_idx)
        q = np.array([joint_state[0] for joint_state in joint_states])
        v = np.array([joint_state[1] for joint_state in joint_states])

        tau_cmd = tau_des - np.multiply(q-q_des, kp_des) - np.multiply(v-v_des, kd_des)

        # Set actuation
        pybullet.setJointMotorControlArray(
            bodyIndex=self.robot,
            jointIndices=self.j_idx,
            controlMode=pybullet.TORQUE_CONTROL,
            forces=tau_cmd
        )

        # Advance simulation by one step
        pybullet.stepSimulation()

