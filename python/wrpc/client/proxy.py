#coding:utf-8

'''
@author: shuai.chen
Created on 2017年3月4日
'''
from __future__ import absolute_import

import time
import functools
import logging
import types

from thrift.transport.TTransport import TTransportException

from wrpc.common.pool import KeyedObjectPool
from wrpc.common.util import singleton

from .factory import ThriftClientFactory

logger = logging.getLogger(__name__)

@singleton
class ClientProxy(object):
    """client proxy class"""
    
    def __init__(self, provider, client_class=ThriftClientFactory, 
                 retry=3, retry_interval=0.2, **kwargs):
        """
        client proxy
        @param provider: server provider,instance of AutoProvider or FixedProvider class
        @param client_class: child class of ClientFactory, default is ThriftClientFactory
        @param retry: retry access times, default is 3
        @param retry_interval: retry interval time, default 0.2s
        @param kwargs: 
            pool_max_size: client pool max size, default is 8    
            pool_wait_timeout: client pool block time, default is None means forever      
        """
        self.__provider = provider
        self.__retry = retry
        self.__retry_interval = retry_interval
        self.__kwargs = kwargs
        
        self.__set_client_factory(client_class)
        self.set_pool()
        
        self.__provider.set_client_proxy(self)
        self.__provider.listen()
        
    def __set_client_factory(self, client_class):
        service_ifaces = self.__provider.get_service_ifaces()
        ifaces = {iface.__name__.split(".")[-1]:iface for iface in service_ifaces}
        self.__client_factory = client_class(self.__provider, ifaces)               
        
    def set_pool(self):
        self.__pool = KeyedObjectPool(self.__client_factory.create, **self.__kwargs)
        logger.info("Client pool setted.")
    
    def get_pool(self):
        return self.__pool
    
    def get_func(self, skey, fun):
        """
        get function 代理函数
        @param skey: service module or module name
        @param fun: service function or function name
        @use:
            func = Client.get_func("UserService", "changeName")
            or
            func = Client.get_func(UserService, UserService.Iface.changeName)
            
            func(*args)
        """
        return functools.partial(self.call, skey, fun)
    
    def call(self, skey, fun, *args):
        """
        直接调用服务端接口
        @param skey: service module or module name
        @param fun: service function or function name
        @param args: args of service function  
        """
        key = skey.__name__.split(".")[-1] if type(skey) == types.ModuleType else skey
        exception = None
        for _ in xrange(self.__retry):
            obj = None
            try:
                obj = self.__pool.borrow_obj(key)
                func = getattr(obj, fun.__name__) if callable(fun) else getattr(obj, fun)
                return func(*args)
            except TTransportException, e:
                exception = e
                logger.error("Could not connect server!")
                time.sleep(self.__retry_interval)
            except Exception, e:
                exception = e
            finally:
                if obj:
                    self.__pool.return_obj(obj, key)
                
        raise exception      
        