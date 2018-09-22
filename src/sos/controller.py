#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.
import sys
import zmq
import time
import threading
from collections import defaultdict
from .utils import env
from .signatures import TargetSignatures, StepSignatures, WorkflowSignatures

# from zmq.utils.monitor import recv_monitor_message

def connect_controllers(context=None):
    if not context:
        env.zmq_context = zmq.Context()
    env.signature_push_socket = env.zmq_context.socket(zmq.PUSH)
    env.signature_push_socket.connect(f'tcp://127.0.0.1:{env.config["sockets"]["signature_push"]}')
    env.signature_req_socket = env.zmq_context.socket(zmq.REQ)
    env.signature_req_socket.connect(f'tcp://127.0.0.1:{env.config["sockets"]["signature_req"]}')

    env.controller_push_socket = env.zmq_context.socket(zmq.PUSH)
    env.controller_push_socket.connect(f'tcp://127.0.0.1:{env.config["sockets"]["controller_push"]}')
    env.controller_req_socket = env.zmq_context.socket(zmq.REQ)
    env.controller_req_socket.connect(f'tcp://127.0.0.1:{env.config["sockets"]["controller_req"]}')

class Controller(threading.Thread):
    def __init__(self, ready):
        threading.Thread.__init__(self)
        self.daemon = True

        self.target_signatures = TargetSignatures()
        self.step_signatures = StepSignatures()
        self.workflow_signatures = WorkflowSignatures()

        self.ready = ready

        # number of active running master processes
        self._nprocs = 0

        self._completed = defaultdict(int)
        self._ignored = defaultdict(int)
        self._subprogressbar_cnt = 0
        # size of sub progress bar
        self._subprogressbar_size = 25
        self._subprogressbar_last_updated = time.time()

        # self.event_map = {}
        # for name in dir(zmq):
        #     if name.startswith('EVENT_'):
        #         value = getattr(zmq, name)
        #          self.event_map[value] = name

    def run(self):
        # there are two sockets
        #
        # signature_push is used to write signatures. It is a single push operation with no reply.
        # signature_req is used to query information. The sender would need to get an response.
        env.zmq_context = zmq.Context()

        sig_push_socket = env.zmq_context.socket(zmq.PULL)
        env.config['sockets']['signature_push'] = sig_push_socket.bind_to_random_port('tcp://127.0.0.1')
        sig_req_socket = env.zmq_context.socket(zmq.REP)
        env.config['sockets']['signature_req'] = sig_req_socket.bind_to_random_port('tcp://127.0.0.1')

        ctl_push_socket = env.zmq_context.socket(zmq.PULL)
        env.config['sockets']['controller_push'] = ctl_push_socket.bind_to_random_port('tcp://127.0.0.1')
        ctl_req_socket = env.zmq_context.socket(zmq.REP)
        env.config['sockets']['controller_req'] = ctl_req_socket.bind_to_random_port('tcp://127.0.0.1')

        #monitor_socket = sig_req_socket.get_monitor_socket()
        # tell others that the sockets are ready
        self.ready.set()
        # Process messages from receiver and controller
        poller = zmq.Poller()
        poller.register(sig_push_socket, zmq.POLLIN)
        poller.register(sig_req_socket, zmq.POLLIN)
        poller.register(ctl_push_socket, zmq.POLLIN)
        poller.register(ctl_req_socket, zmq.POLLIN)
        #poller.register(monitor_socket, zmq.POLLIN)

        if env.verbosity == 1:
            # leading progress bar
            sys.stderr.write('\033[32m[\033[0m')
            sys.stderr.flush()

        while True:
            try:
                socks = dict(poller.poll())

                if sig_push_socket in socks:
                    msg = sig_push_socket.recv_pyobj()
                    try:
                        if msg[0] == 'workflow':
                            self.workflow_signatures.write(*msg[1:])
                        elif msg[0] == 'target':
                            self.target_signatures.set(*msg[1:])
                        elif msg[0] == 'step':
                            self.step_signatures.set(*msg[1:])
                        else:
                            env.logger.warning(f'Unknown message passed {msg}')
                    except Exception as e:
                        env.logger.warning(f'Failed to push signature {msg}: {e}')

                if sig_req_socket in socks:
                    msg = sig_req_socket.recv_pyobj()
                    try:
                        if msg[0] == 'workflow':
                            if msg[1] == 'clear':
                                self.workflow_signatures.clear()
                                sig_req_socket.send_pyobj('ok')
                            elif msg[1] == 'placeholders':
                                sig_req_socket.send_pyobj(self.workflow_signatures.placeholders(msg[2]))
                            elif msg[1] == 'records':
                                sig_req_socket.send_pyobj(self.workflow_signatures.records(msg[2]))
                            else:
                                env.logger.warning(f'Unknown signature request {msg}')
                        elif msg[0] == 'target':
                            if msg[1] == 'get':
                                sig_req_socket.send_pyobj(self.target_signatures.get(msg[2]))
                            else:
                                env.logger.warning(f'Unknown signature request {msg}')
                        elif msg[0] == 'step':
                            if msg[1] == 'get':
                                sig_req_socket.send_pyobj(self.step_signatures.get(*msg[2:]))
                            else:
                                env.logger.warning(f'Unknown signature request {msg}')
                        else:
                            raise RuntimeError(f'Unrecognized signature request {msg}')
                    except Exception as e:
                        env.logger.warning(f'Failed to respond to signature request {msg}: {e}')
                        sig_req_socket.send_pyobj(None)

                if ctl_push_socket in socks:
                    msg = ctl_push_socket.recv_pyobj()
                    try:
                        if msg is None:
                            break
                        elif msg[0] == 'nprocs':
                            env.logger.trace(f'Active running process set to {msg[1]}')
                            self._nprocs = msg[1]
                        elif msg[0] == 'progress':
                            if msg[1] == 'substep_ignored':
                                self._ignored[msg[2]] += 1
                            elif msg[1] == 'substep_completed':
                                self._completed[msg[2]] += 1
                            if env.verbosity == 1:
                                if msg[1] == 'done':
                                    nSteps = len(set(self._completed.keys()) | set(self._ignored.keys()))
                                    nCompleted = sum(self._completed.values())
                                    nIgnored = sum(self._ignored.values())
                                    completed_text = f'{nCompleted} job{"s" if nCompleted > 1 else ""} completed' if nCompleted else ''
                                    ignored_text = f'{nIgnored} job{"s" if nIgnored > 1 else ""} ignored' if nIgnored else ''
                                    steps_text = f'{nSteps} step{"s" if nSteps > 1 else ""} processed'
                                    sys.stderr.write('\b \b'*self._subprogressbar_cnt + f'\033[32m]\033[0m {steps_text} ({completed_text}{", " if nCompleted and nIgnored else ""}{ignored_text})\n')
                                    sys.stderr.flush()
                                else:
                                    # remove existing subworkflow
                                    if time.time() - self._subprogressbar_last_updated > 1:
                                        if self._subprogressbar_cnt == self._subprogressbar_size    :
                                            sys.stderr.write('\b \b'*self._subprogressbar_cnt)
                                            self._subprogressbar_cnt = 0
                                        if msg[1] == 'substep_ignored':
                                            sys.stderr.write(f'\033[90m.\033[0m')
                                            self._subprogressbar_cnt += 1
                                        elif msg[1] == 'substep_completed':
                                            sys.stderr.write(f'\033[32m.\033[0m')
                                            self._subprogressbar_cnt += 1
                                        self._subprogressbar_last_updated = time.time()
                                    if msg[1] == 'step_completed':
                                        if self._subprogressbar_cnt > 0:
                                            sys.stderr.write('\b \b'*self._subprogressbar_cnt)
                                            self._subprogressbar_cnt = 0
                                        if msg[2] == 1:  # completed
                                            sys.stderr.write(f'\033[32m#\033[0m')
                                        elif msg[2] == 0:  # completed
                                            sys.stderr.write(f'\033[90m#\033[0m')
                                        elif msg[2] > 0:  # in the middle
                                            sys.stderr.write(f'\033[36m#\033[0m')
                                        else: # untracked (no signature)
                                            sys.stderr.write(f'\033[33m#\033[0m')
                                    sys.stderr.flush()
                        else:
                            raise RuntimeError(f'Unrecognized request {msg}')
                    except Exception as e:
                        env.logger.warning(f'Failed to push controller {msg}: {e}')

                if ctl_req_socket in socks:
                    msg = ctl_req_socket.recv_pyobj()
                    try:
                        if msg[0] == 'nprocs':
                            ctl_req_socket.send_pyobj(self._nprocs)
                        else:
                            raise RuntimeError(f'Unrecognized request {msg}')
                    except Exception as e:
                        env.logger.warning(f'Failed to respond controller {msg}: {e}')
                # if monitor_socket in socks:
                #     evt = recv_monitor_message(monitor_socket)
                #     if evt['event'] == zmq.EVENT_ACCEPTED:
                #         self._num_clients += 1
                #     elif evt['event'] == zmq.EVENT_DISCONNECTED:
                #         self._num_clients -= 1
            except KeyboardInterrupt:
                break

        sig_push_socket.close()
        sig_req_socket.close()
        ctl_push_socket.close()
        ctl_req_socket.close()