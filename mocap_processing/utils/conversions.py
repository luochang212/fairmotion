import numpy as np
import quaternion

from mocap_processing.utils import constants, utils

import warnings

"""
Glossary:
p: position (3,)
rad: radians
deg: degrees
A: Axis angle (3,)
E: Euler angle (3,)
Q: Quaternion (4,)
R: Rotation matrix (3,3)
T: Transition matrix (4,4)
"""
# TODO: Add batched input support to all conversion methods

def _apply_fn_agnostic_to_vec_mat(input, fn):
    output = np.array([input]) if input.ndim == 1 else input
    output = np.apply_along_axis(fn, 1, output)
    return output[0] if input.ndim == 1 else output


def rad2deg(rad):
    """Convert from radians to degrees."""
    return rad * 180.0 / np.pi


def deg2rad(deg):
    """Convert from degrees to radians."""
    return deg * np.pi / 180.0


def A2A(A):
    return A
    """
    The same 3D orientation could be represented by
    the two different axis-angle representatons;
    (axis, angle) and (-axis, 2pi - angle) where 
    we assume 0 <= angle <= pi. This function forces
    that it only uses an angle between 0 and 2pi.
    """
    def a2a(a):
        angle = np.linalg.norm(a)
        if angle <= constants.EPSILON:
            return a
        if angle > 2*np.pi:
            angle = angle%2*np.pi
            warnings.warn('!!!Angle is larger than 2PI!!!')
        if angle > np.pi:
            return (-a/angle) * (2*np.pi-angle)
        else:
            return a
    
    return _apply_fn_agnostic_to_vec_mat(A, a2a)
    

def A2R(A):
    return quaternion.as_rotation_matrix(quaternion.from_rotation_vector(A))


def A2Q(A):
    return quaternion.as_float_array(quaternion.from_rotation_vector(A))


def R2A(R):
    result = quaternion.as_rotation_vector(quaternion.from_rotation_matrix(R))
    return A2A(result)


def R2E(R):
    """
    Adopted from https://github.com/eth-ait/spl/blob/master/common/
    conversions.py#L76
    Converts rotation matrices to euler angles. This is an adaptation of
    Martinez et al.'s code to work with batched inputs. Original code can be
    found here:
    https://github.com/una-dinosauria/human-motion-prediction/blob/master/src/
    data_utils.py#L12
    Args:
        R: An np array of shape (..., 3, 3) in row-wise arrangement
    Returns:
        An np array of shape (..., 3) containing the Euler angles for each
        rotation matrix in `R`. The Euler angles are in (x, y, z) order
    """

    # Rest of the method assumes row-wise arrangement of rotation matrix R
    assert R.shape[-1] == 3 and R.shape[-2] == 3
    orig_shape = R.shape[:-2]
    rs = np.reshape(R, [-1, 3, 3])
    n_samples = rs.shape[0]

    # initialize to zeros
    e1 = np.zeros([n_samples])
    e2 = np.zeros([n_samples])
    e3 = np.zeros([n_samples])

    # find indices where we need to treat special cases
    is_one = rs[:, 0, 2] == 1
    is_minus_one = rs[:, 0, 2] == -1
    is_special = np.logical_or(is_one, is_minus_one)

    e1[is_special] = np.arctan2(rs[is_special, 0, 1], rs[is_special, 0, 2])
    e2[is_minus_one] = np.pi / 2
    e2[is_one] = -np.pi / 2

    # normal cases
    is_normal = ~np.logical_or(is_one, is_minus_one)
    # clip inputs to arcsin
    in_ = np.clip(rs[is_normal, 0, 2], -1, 1)
    e2[is_normal] = -np.arcsin(in_)
    e2_cos = np.cos(e2[is_normal])
    e1[is_normal] = np.arctan2(
        rs[is_normal, 1, 2] / e2_cos, rs[is_normal, 2, 2] / e2_cos
    )
    e3[is_normal] = np.arctan2(
        rs[is_normal, 0, 1] / e2_cos, rs[is_normal, 0, 0] / e2_cos
    )

    eul = np.stack([e1, e2, e3], axis=-1)
    # Using astype(int) since np.concatenate inadvertently converts elements to
    # float64
    eul = np.reshape(eul, np.concatenate([orig_shape, eul.shape[1:]]).astype(int))
    return eul


def R2Q(R):
    return quaternion.as_float_array(quaternion.from_rotation_matrix(R))


def R2T(R):
    return Rp2T(R, constants.zero_p())


def Q2A(Q):
    result = quaternion.as_rotation_vector(quaternion.as_quat_array(Q))
    return A2A(result)


def Q2E(Q, epsilon=0):
    """
    Adopted from https://github.com/facebookresearch/QuaterNet/blob/
    ce2d8016f749d265da9880a8dcb20a9be1a6d69c/common/quaternion.py#L53
    Convert quaternion(s) Q to Euler angles.
    Order is expected to be "wxyz"
    Expects a tensor of shape (*, 4), where * denotes any number of dimensions.
    Returns a tensor of shape (*, 3).
    """
    assert Q.shape[-1] == 4

    original_shape = list(Q.shape)
    original_shape[-1] = 3
    Q = Q.reshape(-1, 4)

    q0 = Q[:, 0]
    q1 = Q[:, 1]
    q2 = Q[:, 2]
    q3 = Q[:, 3]

    x = np.arctan2(2 * (q0 * q1 - q2 * q3), 1 - 2 * (q1 * q1 + q2 * q2))
    y = np.arcsin(np.clip(2 * (q1 * q3 + q0 * q2), -1 + epsilon, 1 - epsilon))
    z = np.arctan2(2 * (q0 * q3 - q1 * q2), 1 - 2 * (q2 * q2 + q3 * q3))

    E = np.stack([x, y, z], axis=-1)
    return np.reshape(E, original_shape)


def Q2R(Q):
    return quaternion.as_rotation_matrix(quaternion.as_quat_array(Q))


def T2Rp(T):
    R = T[..., :3, :3]
    p = T[..., :3, 3]
    return R, p


def T2Qp(T):
    R, p = T2Rp(T)
    Q = R2Q(R)
    return Q, p


def T2p(T):
    _, p = T2Rp(T)
    return p


def T2R(T):
    R, _ = T2Rp(T)
    return R


def Rp2T(R, p):
    input_shape = R.shape[:-2] if R.ndim > 2 else p.shape[:-1]
    R_flat = R.reshape((-1, 3, 3))
    p_flat = p.reshape((-1, 3))
    T = np.zeros((int(np.prod(input_shape)), 4, 4))
    T[...] = constants.eye_T()
    T[..., :3, :3] = R_flat
    T[..., :3, 3] = p_flat
    return T.reshape(list(input_shape) + [4, 4])


def Qp2T(Q, p):
    R = Q2R(Q)
    return Rp2T(R, p)


def p2T(p):
    return Rp2T(constants.eye_R(), np.array(p))


def Ax2R(theta):
    """
    Convert (axis) angle along x axis Ax to rotation matrix R
    """
    R = constants.eye_R()
    c = np.cos(theta)
    s = np.sin(theta)
    R[1, 1] = c
    R[1, 2] = -s
    R[2, 1] = s
    R[2, 2] = c
    return R


def Ay2R(theta):
    """
    Convert (axis) angle along y axis Ay to rotation matrix R
    """
    R = constants.eye_R()
    c = np.cos(theta)
    s = np.sin(theta)
    R[0, 0] = c
    R[0, 2] = s
    R[2, 0] = -s
    R[2, 2] = c
    return R


def Az2R(theta):
    """
    Convert (axis) angle along z axis Az to rotation matrix R
    """
    R = constants.eye_R()
    c = np.cos(theta)
    s = np.sin(theta)
    R[0, 0] = c
    R[0, 1] = -s
    R[1, 0] = s
    R[1, 1] = c
    return R
    

def Q2Q(Q, op, wxyz_in=True):
    '''
    change_order:
    normalize:
    halfspace:
    '''
    def q2q(q):
        result = q.copy()
        if 'normalize' in op:
            norm = np.linalg.norm(result)
            if norm < constants.EPSILON:
                raise Exception('Invalid input with zero length')
            result /= norm
        if 'halfspace' in op:
            w_idx = 0 if wxyz_in else 3
            if result[w_idx] < 0.0:
                result *= -1.0
        if 'change_order' in op:
            result = result[[1,2,3,0]] if wxyz_in else result[[3,0,1,2]]
        return result
    
    return _apply_fn_agnostic_to_vec_mat(Q, q2q)
