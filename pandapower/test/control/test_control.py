# -*- coding: utf-8 -*-

# Copyright (c) 2016-2019 by University of Kassel and Fraunhofer Institute for Energy Economics
# and Energy System Technology (IEE), Kassel. All rights reserved.

import copy
import pytest
import pandapower.control as ct
import pandapower.networks as networks
import pandapower as pp
from pandapower.control.run_control import get_controller_order
from pandapower.control.basic_controller import Controller
from pandapower.control.controller.trafo_control import TrafoController
from pandapower.control.controller.trafo.ContinuousTapControl import ContinuousTapControl
from pandapower.timeseries.output_writer import OutputWriter
from pandapower.timeseries.run_time_series import run_timeseries

try:
    import pplog
except:
    import logging as pplog

logger = pplog.getLogger(__name__)
ctrl_logger = pplog.getLogger("hp.control.control_handler")
logger.setLevel(pplog.CRITICAL)


@pytest.fixture
def net():
    net = networks.create_kerber_vorstadtnetz_kabel_1()

    for i, load in net.load.iterrows():
        pp.create_sgen(net, load.bus, p_mw=1*1e-3, sn_mva=2*1e-3)

    return net


def test_add_get_controller(net):
    # dummy controller
    class ControllerTester(Controller):
        def __init__(self, net, bus, p, q, name):
            super().__init__(net)
            self.name = name

        def time_step(self, net, time):
            pass

        def control_step(self, net):
            pass

        def is_converged(self):
            return True

    # creating a test controller
    my_controller = ControllerTester(net, 0, -1, 2, name="test")

    # assert that we get, what we set
    assert net.controller.controller.at[my_controller.index] is my_controller


def test_ctrl_unconverged(net):
    output_writer = OutputWriter(net, time_steps=[0, 1])

    class DivergentController(Controller):
        def __init__(self, net):
            super().__init__(net)

        def time_step(self, time):
            self.convergent = True if time % 2 == 0 else False

        def is_converged(self):
            return self.convergent

    DivergentController(net)

    with pytest.raises(ct.ControllerNotConverged):
        run_timeseries(net, time_steps=range(0, 3), output_writer=output_writer, max_iter=3)

    # assert no exceptions but appropriate output in outputwriter
    run_timeseries(net, time_steps=range(0, 3), output_writer=output_writer, max_iter=3,
                   continue_on_divergence=True)

    for i, out in enumerate(output_writer.output["Parameters"].controller_unstable):
        if i % 2 == 0:
            assert not out
        else:
            assert out

def test_conflicting_controllers(net):
    # several controllers for the same element, with different setpoints
    # this is wrong, ch.run_loadflow must fail in such situation!
    tol = 1e-6
    ContinuousTapControl(net, 0, u_set=0.98, tol=tol, order=0)
    ContinuousTapControl(net, 0, u_set=1.02, tol=tol, order=1)
    ContinuousTapControl(net, 0, u_set=1.05, tol=tol, order=2)

    with pytest.raises(ct.ControllerNotConverged):
        ct.run_control(net)


def test_in_service_bool(net):
    # make sure fails with something other than bool
    with pytest.raises(KeyError):
        cnet = copy.deepcopy(net)
        TrafoController(cnet, 0,  side = "lv", trafotype="2W", level=1, in_service="True", tol=1e-6)
        ct.run_control(cnet)
    with pytest.raises(KeyError):
        cnet = copy.deepcopy(net)
        TrafoController(cnet, 0, side = "lv", trafotype="2W", level=1, in_service=1.0, tol=1e-6)
        ct.run_control(cnet)
    with pytest.raises(TypeError):
        cnet = copy.deepcopy(net)
        TrafoController(cnet, 0,side = "lv", trafotype="2W", level=1, in_service=[1, 2, 3], tol=1e-6)
        ct.run_control(cnet)


def test_multiple_levels(net):
    TrafoController(net, 0, side = "lv", trafotype="2W", level=1, tol = 1e-6, in_service=True)
    Controller(net, gid=2, level=[1, 2])
    Controller(net, gid=2, level=[1, 2])
    level, order = get_controller_order(net)
    # three levels with unspecific controller order => in order of appearance
    # assert order == [[0, 1], [1,2]]
    assert len(order) == 2
    assert order[0][0].index == 0
    assert order[0][1].index == 1
    assert order[1][0].index == 1
    assert order[1][1].index == 2

    assert level == [1, 2]
    ct.run_control(net)


if __name__ == '__main__':
     pytest.main(['-s', __file__])
