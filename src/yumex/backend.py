#    Yum Exteder (yumex) - A graphic package management tool
#    Copyright (C) 2013-2014 Tim Lauridsen < timlau<AT>fedoraproject<DOT>org >
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to
#    the Free Software Foundation, Inc.,
#    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA


import logging

import yumex.const as const

logger = logging.getLogger('yumex.backend')


class Package:
    """
    Base class for a package, must be implemented in a sub class
    """

    def __init__(self, backend):
        self.backend = backend
        self.name = None
        self.arch = None
        self.repository = None
        self.summary = None
        self.size = None
        self.action = None
        self.queued = False
        self.recent = False
        self.selected = False

    def __str__(self):
        """
        Return a string representation of the package
        """
        return self.fullname

    @property
    def fullname(self):
        """
        fullname for the package :name-version.arch
        """
        return "%s-%s.%s" % (self.name, self.version, self.arch)

    def get_attribute(self, attr):
        """
        get attribute for the package
        :param attr:
        """
        if hasattr(self, attr):
            return getattr(self, attr)
        else:
            return self.do_get_atributes(attr)

    def do_get_atributes(self, attr):
        """
        get non local attributes for the package
        must be implemented in a sub class
        :param attr:
        """
        raise NotImplementedError()

    def exception_handler(self, e):
        """
        send exceptions to the frontend
        """
        self.backend.frontend.exception_handler(e)


class Backend:
    """
    Base package manager handling class
    it contains a cache for Package based objects, so we don't have
    to get the twice from the package manager.

    must be implemented in a sub class
    """

    def __init__(self, frontend, filters=False):
        if filters:
            self.cache = PackageCacheWithFilters()
        else:
            self.cache = PackageCache()
        self.has_filters = filters
        self.frontend = frontend

    def get_filter(self, name):
        if self.has_filters:
            return self.cache.filters.get(name)
        else:
            return None

    def exception_handler(self, e):
        """
        send exceptions to the frontend
        """
        self.frontend.exception_handler(e)

    def get_packages(self, pkg_filter):
        """ Get a list of Package objects based on a filter
        ('installed', 'available'...)
        """
        pkgs = self.cache._get_packages(pkg_filter)
        return pkgs


class BaseFilter:
    """Used as base for filters, there can filter a list of packages
    based on a different conditions
    """

    def __init__(self, name, active=False):
        self.name = name
        self.active = active

    def run(self, pkgs):
        if not self.active:
            return pkgs

    def change(self, archs):
        pass

    def set_active(self, state):
        self.active = state


class ArchFilter(BaseFilter):
    """
    Arch Filter to filter a list of packages by arch
    """

    def __init__(self, name, active=False):
        BaseFilter.__init__(self, name, active)
        self.archs = ['noarch', 'i686', 'x86_64']

    def run(self, pkgs):
        BaseFilter.run(self, pkgs)
        filtered = [po for po in pkgs if po.arch in self.archs]
        return filtered

    def change(self, archs):
        self.archs = archs


class Filters:
    """
    Container to contain a number of filters based on the BaseFilter class
    """

    def __init__(self):
        self._filters = {}

    def add(self, filter_cls):
        if filter_cls.name not in self._filters:
            self._filters[filter_cls.name] = filter_cls

    def delete(self, name):
        if name in self._filters:
            del self._filters[name]

    def run(self, pkgs):
        flt_pkgs = pkgs
        for name in self._filters:
            flt_pkgs = self._filters[name].run(flt_pkgs)
        return flt_pkgs

    def get(self, name):
        if name in self._filters:
            return self._filters[name]
        else:
            return None


class PackageCache:
    """
    Package cache to contain packages from backend,
    so we dont have get them more than once.
    """

    def __init__(self):
        """
        setup the cache
        """
        for flt in const.ACTIONS_FILTER.values():
            setattr(self, flt, set())
        self._populated = []
        self._index = {}

    def reset(self):
        """
        reset the cache
        """
        for flt in const.ACTIONS_FILTER.values():
            setattr(self, flt, set())
        self._populated = []
        self._index = {}

    def _get_packages(self, pkg_filter):
        """
        get a list of packages from the cache
        @param pkg_filter: the type of packages to get
        """
        pkgs = list(getattr(self, str(pkg_filter)))
        return pkgs

    def is_populated(self, pkg_filter):
        return str(pkg_filter) in self._populated

    def populate(self, pkg_filter, pkgs):
        """
        """
        self.find_packages(pkgs)
        self._populated.append(str(pkg_filter))

    def _add(self, po):
        if str(po) in self._index:  # package is in cache
            return self._index[str(po)]
        else:
            target = getattr(self, const.ACTIONS_FILTER[po.action])
            self._index[str(po)] = po
            target.add(po)
            return po

    # @TimeFunction
    def find_packages(self, packages):
        pkgs = []
        i = 0
        if packages:
            for po in packages:
                i += 1
                pkgs.append(self._add(po))
            return pkgs
        else:
            return []


class PackageCacheWithFilters(PackageCache):
    """ Package cache to contain packages from backend,
    so we dont have get them more than once.
    This version has filtering, so we can filter packages by fx. arch
    """

    def __init__(self):
        """
        setup the cache
        """
        PackageCache.__init__(self)
        self.filters = Filters()
        arch_flt = ArchFilter('arch')
        self.filters.add(arch_flt)

    def _get_packages(self, pkg_filter):
        """
        get a list of packages from the cache
        @param pkg_filter: the type of packages to get
        """
        pkgs = PackageCache._get_packages(self, str(pkg_filter))
        pkgs = self.filters.run(pkgs)
        return pkgs

    # @TimeFunction
    def find_packages(self, packages):
        pkgs = PackageCache.find_packages(self, packages)
        pkgs = self.filters.run(pkgs)
        return pkgs
