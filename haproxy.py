# haproxy-collectd-plugin - haproxy.py
#
# Author: Michael Leinartas
# Original code: https://github.com/mleinart/collectd-haproxy/master/haproxy.py
# Description: This is a collectd plugin which runs under the Python plugin to
# collect metrics from haproxy.
# Plugin structure and logging func taken from:
# https://github.com/phrawzty/rabbitmq-collectd-plugin

# James Sumners Note:
# The base of this plugin is indeed taken from the aforementioned original
# source. It also includes work from GitHub user "zerthimon", namely, the
# multi-instance support. But the end result is almost a complete rewrite
# to simplify some things and add in threading.

import collectd
import socket
import csv
import threading

PLUGIN_NAME='haproxy'
METRIC_DELIM='.'

METRIC_TYPES = {
    'qcur': 'queue_current',
    'scur': 'sessions_current',
    'slim': 'sessions_limit',
    'stot': 'sessions_total',
    'bin': 'bytes_in',
    'bout': 'bytes_out',
    'dreq': 'requests_denied',
    'dresp': 'response_denied',
    'ereq': 'requests_error',
    'econ': 'connection_error',
    'eresp': 'response_error',
    'wretr': 'server_retries',
    'wredis': 'redispatched',
    'chkfail': 'checks_failed',
    'downtime': 'downtime',
    'lbtot': 'selection_total',
    'rate': 'session_rate',
    'hrsp_1xx': 'response_1xx',
    'hrsp_2xx': 'response_2xx',
    'hrsp_3xx': 'response_3xx',
    'hrsp_4xx': 'response_4xx',
    'hrsp_5xx': 'response_5xx',
    'hrsp_other': 'response_other',
    'req_rate': 'request_rate',
    'cli_abrt': 'aborts_client',
    'srv_abrt': 'aborts_server',
    'comp_in': 'compressor_in',
    'comp_out': 'compressor_out',
    'comp_byp': 'compressor_byp',
    'comp_rsp': 'compressor_resp',
    'qtime': 'queue_time_ms',
    'ctime': 'connect_time_ms',
    'rtime': 'response_time_ms',
    'ttime': 'session_time_ms',
    'Uptime_sec': 'uptime_seconds',
    'CurrConns': 'current_connections',
    'CumConns': 'cumulative_connections',
    'CumReq': 'cumulative_requests',
    'CurrSslConns': 'current_ssl_connections',
    'CumSslConns': 'cumulative_ssl_connections',
    'PipesUsed': 'pipes_used',
    'PipesFree': 'pipes_free',
    'ConnRate': 'connections_rate',
    'SessRate': 'sessions_rate',
    'SslRate': 'connections_ssl_rate',
    'CompressBpsIn': 'compression_bps_in',
    'CompressBpsOut': 'compression_bps_out',
    'Tasks': 'tasks',
    'Run_queue': 'run_queue',
    'Idle_pct': 'CPU_percent_idle'
}

class Logger(object):
    """Logger is a wrapper around the collectd logging functions."""
    def __init__(self, prefix, verbose=False):
        super(Logger, self).__init__()
        self.prefix = prefix
        self.verbose = verbose

    def __repr__(self):
        return '{prefix: "%s", verbose: "%s"}' % (self.prefix, self.verbose)

    def _log(self, level, msg, params):
        message = msg
        if not params is None:
            message = msg % params
        message = '%s: %s' % (self.prefix, message)

        if level is 'debug' and self.verbose:
            # because we want our debug messages printed
            # regardless of collectd's debug state
            # we use the notice method
            collectd.notice(message)
        elif level is 'debug' and not self.verbose:
            return
        elif level is 'error':
            collectd.error(message)
        elif level is 'info':
            collectd.info(message)
        elif level is 'notice':
            collectd.notice(message)
        elif level is 'warn':
            collectd.warning(message)
        else:
            collectd.info(message)

    def debug(self, msg, *params):
        self._log('debug', msg, params)

    def error(self, msg, *params):
        self._log('error', msg, params)

    def info(self, msg, *params):
        self._log('info', msg, params)

    def notice(self, msg, *params):
        self._log('notice', msg, params)

    def warn(self, msg, *params):
        self._log('warn', msg, params)

# https://github.com/memsql/memsql-collectd/blob/master/memsql_collectd/plugin.py
class _AttrDict(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, val):
        self[name] = val

class ConfigInstance(object):
    def __init__(self, name = None, log = None):
        super(ConfigInstance, self).__init__()
        self.name = name
        self.log = log
        self.verbose = False
        self.interval = 10
        self.socket = '/var/run/haproxy.sock'
        self.recv_size = 1024
        self.proxies = _AttrDict(monitor=[], ignore=[])

    def __repr__(self):
        return '{name: "%s", verbose: "%s", interval: "%s", socket: "%s", recv_size: "%s", proxies: "%s"}' % (
            self.name, self.verbose, self.interval, self.socket, self.recv_size, self.proxies)



CONFIG = _AttrDict(
    handler = None,
    instances = [],
    root = ConfigInstance('root', Logger(PLUGIN_NAME))
)

class HAProxySocket(object):
    def __init__(self, socket_file, recv_size = 1024):
        self.recv_size = recv_size
        self.socket_file = socket_file
        self.log = Logger('HAProxySocket', CONFIG.root.verbose)

    def connect(self):
        self.log.debug('connect')
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.socket_file)
        return s

    def communicate(self, command):
        self.log.debug('communicate')
        ''' Send a single command to the socket and return a single response (raw string) '''
        s = self.connect()
        if not command.endswith('\n'): command += '\n'
        s.send(command)
        result = ''
        buf = ''
        buf = s.recv(self.recv_size)
        while buf:
            result += buf
            buf = s.recv(self.recv_size)
        s.close()
        return result

    def get_server_info(self):
        self.log.debug('get_server_info')
        result = {}
        output = self.communicate('show info')
        for line in output.splitlines():
            try:
                key,val = line.split(':')
            except ValueError, e:
                continue
            result[key.strip()] = val.strip()
        self.log.debug('server_info: %s', result)
        return result

    def get_server_stats(self):
        self.log.debug('get_server_stats')
        output = self.communicate('show stat')
        #sanitize and make a list of lines
        output = output.lstrip('# ').strip()
        output = [ l.strip(',') for l in output.splitlines() ]
        csvreader = csv.DictReader(output)
        result = [ d.copy() for d in csvreader ]
        self.log.debug('server_stats: %s', result)
        return result

class Handler(threading.Thread):
    """
        Handler is used to actually communicate with the HAProxy sockets
        and send them to the remote Carbon server. Each interval will
        get its own thread for doing all of the operations necessary to
        complete the stats gathering and sending.
    """
    def __init__(self, config):
        super(Handler, self).__init__()
        self.log = Logger('handler', config.root.verbose)
        self.config = config

    def get_stats(self, instance):
        instance.log.debug('getting stats for instance: %s', instance.name)

        stats = {}
        haproxy = HAProxySocket(instance.socket, instance.recv_size)

        try:
            server_info = haproxy.get_server_info()
            server_stats = haproxy.get_server_stats()
        except socket.error, e:
            instance.log.error('Unable to connect to HAProxy socket at %s',
                      instance.socket)
            return stats

        metrics = METRIC_TYPES.keys()

        if 'server' in instance.proxies.monitor:
            for key, val in server_info.items():
                if not key in metrics:
                    continue
                metricname = METRIC_DELIM.join([instance.name, key])
                instance.log.debug('info metricname: %s', metricname)
                try:
                    stats[metricname] = int(val)
                    instance.log.debug('%s = %s', metricname, stats[metricname])
                except:
                    instance.log.debug('could not parse value for: %s', metricname)
                    pass

        for statdict in server_stats:
            if not ('all' in instance.proxies.monitor or
                    '*' in instance.proxies.monitor or
                    statdict['svname'].lower() in instance.proxies.monitor or
                    statdict['pxname'].lower() in instance.proxies.monitor):
                instance.log.debug('not processing proxy: %s', statdict['pxname'])
                continue
            if statdict['pxname'].lower() in instance.proxies.ignore:
                instance.log.debug('ignoring proxy: %s', statdict['pxname'])
                continue

            for key, val in statdict.iteritems():
                if not key in metrics:
                    continue
                metricname = METRIC_DELIM.join([instance.name,
                                                statdict['pxname'].lower(), key])
                instance.log.debug('stat metricname: %s', metricname)
                try:
                    stats[metricname] = int(val)
                    instance.log.debug('%s = %s', metricname, stats[metricname])
                except (TypeError, ValueError), e:
                    instance.log.debug('cold not parse value for: %s', metricname)
                    pass

        instance.log.debug('stats: %s', stats)
        return stats

    def send_stats(self, instance, stats):
        instance.log.debug('sending stats')
        metrics = METRIC_TYPES.keys()
        instance.log.debug('metrics: %s', metrics)
        instance.log.debug('items: %s', stats.items())
        for key, value in stats.iteritems():
            instance.log.debug('stat: (%s, %s)', key, value)
            key_prefix, key_root = key.rsplit(METRIC_DELIM, 1)
            val = collectd.Values(plugin=key_prefix, type=METRIC_TYPES[key_root])
            val.values = [value]
            instance.log.debug('sending: (%s, %s)', val, value)
            val.dispatch()

    def run(self):
        self.log.debug('config: %s', self.config)
        stats = self.get_stats(self.config.root)
        if len(stats.keys()) > 0:
            self.send_stats(self.config.root, stats)

        for instance in self.config.instances:
            stats = self.get_stats(instance)
            if len(stats.keys()) > 0:
                self.send_stats(instance, stats)

def init_callback(data):
    data.handler = Handler(data)
    collectd.register_read(data.handler.run)

def read_config_obj(config, instance):
    for node in config.children:
        if node.key == 'ReceiveSize':
            instance.recv_size = node.values[0]
        if node.key == 'ProxyMonitor':
            instance.proxies.monitor.append(node.values[0])
        elif node.key == 'ProxyIgnore':
            instance.proxies.ignore.append(node.values[0])
        elif node.key == 'Socket':
            instance.socket = node.values[0]
        elif node.key == 'Verbose':
            verbose = bool(node.values[0])
            instance.verbose = verbose
            instance.log = Logger(instance.name, verbose)
        elif node.key == 'Instance':
            continue
        else:
            continue

    if instance.log is None:
        instance.log = Logger(instance.name, instance.verbose)

    if len(instance.proxies.monitor) == 0:
        instance.proxies.monitor = ['server', 'frontend', 'backend']
    instance.proxies.monitor = [p.lower() for p in instance.proxies.monitor]
    if len(instance.proxies.ignore) > 0:
        instance.proxies.ignore = [p.lower() for p in instance.proxies.lower]
    instance.log.debug('instance: %s', instance)

def config_callback(config, data):
    if config.key.lower() == 'module':
        # root node
        read_config_obj(config, data.root)
        for node in config.children:
            # instance nodes
            if len(node.values) == 0:
                continue
            if node.key.lower() == 'instance':
                instance = ConfigInstance(name = node.values[0])
                read_config_obj(node, instance)
                data.instances.append(instance)

collectd.register_init(init_callback, CONFIG)
collectd.register_config(config_callback, CONFIG)
