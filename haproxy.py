# haproxy-collectd-plugin - haproxy.py
#
# Author: Michael Leinartas
# Original code: https://github.com/mleinart/collectd-haproxy/master/haproxy.py
# Description: This is a collectd plugin which runs under the Python plugin to
# collect metrics from haproxy.
# Plugin structure and logging func taken from:
# https://github.com/phrawzty/rabbitmq-collectd-plugin

import collectd
import socket
import csv

NAME = 'haproxy'
PLUGIN_NAME = NAME
RECV_SIZE = 1024
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

METRIC_DELIM = '.' # for the frontend/backend stats

DEFAULT_PROXY_MONITORS = [ 'server', 'frontend', 'backend' ]

VERBOSE_LOGGING = False

CONFIG_INSTANCES = []
CONFIG_ROOT = {}

class Logger(object):
    def __init__(self, prefix, verbose=False):
        self.prefix = prefix
        self.verbose = verbose

    def error(self, msg):
        collectd.error('{name}: {msg}'.format(name=self.prefix, msg=msg))

    def notice(self, msg):
        collectd.notice('{name}: {msg}'.format(name=self.prefix, msg=msg))

    def warn(self, msg):
        collectd.warning('{name}: {msg}'.format(name=self.prefix, msg=msg))

    def debug(self, msg):
        if self.verbose or VERBOSE_LOGGING:
            collectd.info('{name}: {msg}'.format(name=self.prefix, msg=msg))

log = Logger('haproxy global')

class HAProxySocket(object):
    def __init__(self, socket_file):
        self.socket_file = socket_file
        self.log = Logger('HAProxySocket')

    def connect(self):
        self.log.debug('method: connect')
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.socket_file)
        return s

    def communicate(self, command):
        self.log.debug('method: communicate')
        ''' Send a single command to the socket and return a single response (raw string) '''
        s = self.connect()
        if not command.endswith('\n'): command += '\n'
        s.send(command)
        result = ''
        buf = ''
        buf = s.recv(RECV_SIZE)
        while buf:
            result += buf
            buf = s.recv(RECV_SIZE)
        s.close()
        return result

    def get_server_info(self):
        self.log.debug('method: get_server_info')
        result = {}
        output = self.communicate('show info')
        for line in output.splitlines():
            try:
                key,val = line.split(':')
            except ValueError, e:
                continue
            result[key.strip()] = val.strip()
        self.log.debug('server_info: %s' % result)
        return result

    def get_server_stats(self):
        self.log.debug('method: get_server_stats')
        output = self.communicate('show stat')
        #sanitize and make a list of lines
        output = output.lstrip('# ').strip()
        output = [ l.strip(',') for l in output.splitlines() ]
        csvreader = csv.DictReader(output)
        result = [ d.copy() for d in csvreader ]
        self.log.debug('server_stats: %s' % result)
        return result

### Module functions

def get_stats(instance_config):
    log.debug('function: get_stats')
    instance_name, config_data = instance_config.items()[0]
    _log = config_data['log']
    _log.debug("instance_name: %s" % instance_name)
    _log.debug("config_data: %s" % config_data)

    stats = {}
    haproxy = HAProxySocket(config_data['HAPROXY_SOCKET'])

    try:
        server_info = haproxy.get_server_info()
        server_stats = haproxy.get_server_stats()
    except socket.error, e:
        _log.warn('status err Unable to connect to HAProxy socket at %s' %
                  config_data['HAPROXY_SOCKET'])
        return stats

    if 'server' in config_data['PROXY_MONITORS']:
        for key, val in server_info.items():
            if instance_name == 'root':
                key_prefix = server_info['Name']
            else:
                key_prefix = instance_name + METRIC_DELIM + server_info['Name']
            metricname = METRIC_DELIM.join([key_prefix , key])
            _log.debug('metricname: %s' % metricname)
            try:
                stats[metricname] = int(val)
                _log.debug('%s = %s' % (metricname, stats[metricname]))
            except (TypeError, ValueError), e:
                _log.debug('could not parse value for: %s' % metricname)
                pass

    for statdict in server_stats:
        if not ('all' in config_data['PROXY_MONITORS'] or \
                '*' in config_data['PROXY_MONITORS']):
            if not (statdict['svname'].lower() in config_data['PROXY_MONITORS'] or \
                    statdict['pxname'].lower() in config_data['PROXY_MONITORS']):
                _log.debug(
                    '(svname = %s, pxname = %s) not being processed' %
                    (statdict['svname'], statdict['pxname'])
                )
                continue

            if statdict['pxname'] in config_data['PROXY_IGNORE']:
                _log.debug('(pxname = %s) not being processed' % statdict['pxname'])
                continue

        for key, val in statdict.items():
            if instance_name == 'root':
                key_prefix = statdict['svname']
            else:
                key_prefix = instance_name + METRIC_DELIM + statdict['svname']
            metricname = METRIC_DELIM.join([key_prefix.lower(),
                                            statdict['pxname'].lower(), key])
        _log.debug('metricname: %s' % metricname)
        try:
            stats[metricname] = int(val)
            _log.debug('%s = %s' % (metricname, stats[metricname]))
        except (TypeError, ValueError), e:
            _log.debug('cold not parse value for: %s' % metricname)
            pass
    return stats

def get_instance_config(config_child, instance_name):
    log.debug('function: get_instance_config')
    instance_config = {
        'PROXY_MONITORS': [],
        'PROXY_IGNORE': [],
        'HAPROXY_SOCKET': '/var/lib/haproxy/stats',
        'VERBOSE_LOGGING': False
    }

    for node in config_child.children:
        if node.key == 'ProxyMonitor':
            instance_config['PROXY_MONITORS'].append(node.values[0])
        elif node.key == 'ProxyIgnore':
            instance_config['PROXY_IGNORE'].append(node.values[0])
        elif node.key == 'Socket':
            instance_config['HAPROXY_SOCKET'] = node.values[0]
        elif node.key == 'Verbose':
            VERBOSE_LOGGING = bool(node.values[0])
            instance_config['log'] = Logger(instance_name, VERBOSE_LOGGING)
        elif node.key == 'Instance':
            continue
        else:
            log.warn('Unknown config key: %s' % node.key)

        if not instance_config['PROXY_MONITORS']:
            instance_config['PROXY_MONITORS'] = DEFAULT_PROXY_MONITORS
        instance_config['PROXY_MONITORS'] = [p.lower() for p in
                                             instance_config['PROXY_MONITORS']]

    return instance_config

def configure_callback(conf):
    log.debug('function: configure_callback')
    for node in conf.children:
        if node.children:
            # instance config
            if node.key == 'Instance':
                instance_name = node.values[0]
            else:
                instance_name = node.key
            CONFIG_INSTANCES.append({
                instance_name: get_instance_config(node, instance_name)
            })
        else:
            # root config
            CONFIG_ROOT = {'root': get_instance_config(conf, 'root')}

def read_callback():
    log.debug('function: read_callback')

    if CONFIG_INSTANCES:
        info = {}
        for config_instance in CONFIG_INSTANCES:
            info.update(get_stats(config_instance))
            if not info:
                log.warn('%s: No data received from %s instance' %
                        (NAME, config_instance.keys()[0]))
    else:
        info = get_stats(CONFIG_ROOT)
        if not info:
            log.warn('%s: No data received' % NAME)

    for key,value in info.iteritems():
        key_prefix, key_root = key.rsplit(METRIC_DELIM,1)
        if not key_root in METRIC_TYPES:
            continue

        val = collectd.Values(plugin=NAME + METRIC_DELIM + key_prefix,
                              type=METRIC_TYPES[key_root])
        val.values = [value]
        log.debug('%s, %s' % (val, value))
        val.dispatch()

collectd.register_config(configure_callback)
collectd.register_read(read_callback)
