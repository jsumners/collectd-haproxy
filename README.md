collectd-haproxy
================
This is a collectd plugin to pull HAProxy (<http://haproxy.1wt.eu>) stats from the HAProxy management socket.
It is written in Python and as such, runs under the collectd Python plugin.

Requirements
------------

*HAProxy*  
To use this plugin, HAProxy must be configured to create a management socket with the `stats socket`
configuration option. collectd must have read/write access to the socket.

*collectd*  
collectd must have the Python plugin installed. See (<http://collectd.org/documentation/manpages/collectd-python.5.shtml>)

Options
-------
* `ProxyMonitor`  
Proxy to monitor. If unset, defaults to ['server', 'frontend', 'backend'].
Specify multiple times to specify additional proxies, or use either of the
special values "all" or "*" to select all proxies
* `ProxyIgnore`  
One or more Proxies to ignore
 Specify multiple times to specify additional proxies
* `Socket`  
File location of the HAProxy management socket
* `Verbose`  
Enable verbose logging
* `Instance`
There are situations when multiple instances of HAProxy needs to run on the same host

Example
-------
    TypesDB "/usr/share/collectd/haproxy_types.db"

    <LoadPlugin python>
        Globals true
    </LoadPlugin>

    <Plugin python>
        # haproxy.py is at /usr/lib64/collectd/haproxy.py
        ModulePath "/usr/lib64/collectd/"

        Import "haproxy"

        <Module haproxy>
          Socket "/var/run/haproxy.sock"
          ProxyMonitor "server"
          ProxyMonitor "backend"
        </Module>
    </Plugin>

Example Multi-Instance
----------------------
    TypesDB "/usr/share/collectd/haproxy_types.db"

    <LoadPlugin python>
        Globals true
    </LoadPlugin>

    <Plugin python>
        # haproxy.py is at /usr/lib64/collectd/haproxy.py
        ModulePath "/usr/lib64/collectd/"

        Import "haproxy"

        <Module haproxy>
          <Instance haproxy1>
              Socket "/var/run/haproxy1.sock"
              ProxyMonitor "server"
              ProxyMonitor "backend"
          </Instance>
          <Instance haproxy2>
              Socket "/var/run/haproxy2.sock"
              ProxyMonitor "server"
              ProxyMonitor "backend"
          </Instance>
        </Module>
    </Plugin>
