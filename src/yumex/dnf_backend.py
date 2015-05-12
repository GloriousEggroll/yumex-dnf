# -*- coding: iso-8859-1 -*-
#    Yum Exteder (yumex) - A graphic package management tool
#    Copyright (C) 2013 Tim Lauridsen < timlau<AT>fedoraproject<DOT>org >
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


from __future__ import absolute_import

from yumex.misc import ExceptionHandler, TimeFunction, _, CONFIG
from gi.repository import Gdk

import dnfdaemon.client
import logging
import yumex.backend
import yumex.misc
import yumex.const as const

logger = logging.getLogger('yumex.yum_backend')


class DnfPackage(yumex.backend.Package):
    """Abstract package object for a package in the package system."""

    def __init__(self, po_tuple, action, backend):
        yumex.backend.Package.__init__(self, backend)
        (pkg_id, summary, size) = po_tuple
        self.pkg_id = pkg_id
        self.action = action
        (n, e, v, r, a, repo_id) = yumex.misc.to_pkg_tuple(self.pkg_id)
        self.name = n
        self.epoch = e
        self.ver = v
        self.rel = r
        self.arch = a
        self.repository = repo_id
        self.visible = True
        self.selected = False
        self.downgrade_po = None
        self.summary = summary
        self.size = size
        self.sizeM = yumex.misc.format_number(size)
        # cache
        self._description = None

    def __str__(self):
        """String representation of the package object."""
        return self.fullname

    @property
    def fullname(self):
        return yumex.misc.id2fullname(self.pkg_id)

    @ExceptionHandler
    def get_attribute(self, attr):
        """Get a given attribute for a package."""
        return self.backend.GetAttribute(self.pkg_id, attr)

    @property
    def version(self):
        return self.ver

    @property
    def release(self):
        return self.rel

    @property
    def filename(self):
        """RPM filename of a package."""
        # the full path for at localinstall is stored in repoid
        if self.action == 'li':
            return self.repoid
        else:
            return "%s-%s.%s.%s.rpm" % (self.name, self.version,
                                        self.release, self.arch)

    @property
    def fullver(self):
        """Package full version-release."""
        return "%s-%s" % (self.version, self.release)

    @property
    def installed(self):
        return self.repository[0] == '@'

    @property
    def URL(self):
        return self.get_attribute('url')

    def set_select(self, state):
        """Package is selected in package view."""
        self.selected = state

    def set_visible(self, state):
        """Package is visible in package view"""
        self.visible = state

    @property
    def description(self):
        return self.get_attribute('description')

    @property
    def changelog(self):
        return self.get_attribute('changelog')

    @property
    def filelist(self):
        return self.get_attribute('filelist')

    @property
    def pkgtags(self):
        return self.get_attribute('pkgtags')

    @property
    def color(self):
        """Package color to show in package view."""
        color = CONFIG.conf.color_normal
        if self.action == 'u':
            color = CONFIG.conf.color_update
        elif self.action == 'o':
            color = CONFIG.conf.color_obsolete
        elif self.action == 'do':
            color = CONFIG.conf.color_downgrade
        elif self.action == 'r':
            color = CONFIG.conf.color_install
        rgba = Gdk.RGBA()
        rgba.parse(color)
        return rgba

    @property
    @ExceptionHandler
    def downgrades(self):
        return self.backend.get_downgrades(self.pkg_id)

    @property
    @ExceptionHandler
    def updateinfo(self):
        return self.get_attribute('updateinfo')

    @property
    @ExceptionHandler
    def requirements(self):
        return  self.get_attribute('requires')

    @property
    def is_update(self):
        """Package is an update/replacement to another package."""
        if self.action == 'o' or self.action == 'u':
            return True
        else:
            return False


class DnfRootBackend(yumex.backend.Backend, dnfdaemon.client.Client):
    """Backend to do all the dnf related actions """

    def __init__(self, frontend):
        yumex.backend.Backend.__init__(self, frontend, filters=True)
        dnfdaemon.client.Client.__init__(self)
        self._gpg_confirm = None
        self.dnl_progress = None
        self._files_to_download = 0
        self._files_downloaded = 0

    def on_TransactionEvent(self, event, data):
        if event == 'start-run':
            self.frontend.infobar.show_progress(True)
        elif event == 'download':
            self.frontend.infobar.info(_('Downloading packages'))
        elif event == 'pkg-to-download':
            self._dnl_packages = data
        elif event == 'signature-check':
            # self.frontend.infobar.show_progress(False)
            self.frontend.infobar.set_progress(0.0)
            self.frontend.infobar.info(_('Checking packages signatures'))
            self.frontend.infobar.set_progress(1.0)
            self.frontend.infobar.info_sub('')
        elif event == 'run-test-transaction':
            # self.frontend.infobar.info(_('Testing Package Transactions')) #
            # User don't care
            pass
        elif event == 'run-transaction':
            self.frontend.infobar.show_progress(True)
            self.frontend.infobar.info(_('Applying changes to the system'))
            self.frontend.infobar.hide_sublabel()
        elif event == 'verify':
            self.frontend.infobar.show_progress(True)
            self.frontend.infobar.info(_('Verify changes on the system'))
            #self.frontend.infobar.hide_sublabel()
        # elif event == '':
        elif event == 'fail':
            self.frontend.infobar.show_progress(False)
        elif event == 'end-run':
            self.frontend.infobar.show_progress(False)
        else:
            logger.debug('TransactionEvent : %s' % event)

    def on_RPMProgress(self, package, action, te_current,
                       te_total, ts_current, ts_total):
        num = ' ( %i/%i )' % (ts_current, ts_total)
        if ',' in package:  # this is a pkg_id
            name = self._fullname(package)
        else:  # this is just a pkg name (cleanup)
            name = package
        logger.debug('on_RPMProgress : [%s]' % package)
        self.frontend.infobar.info_sub(const.RPM_ACTIONS[action] % name)
        if ts_current > 0 and ts_current <= ts_total:
            frac = float(ts_current) / float(ts_total)
            self.frontend.infobar.set_progress(frac, label=num)

    def on_GPGImport(self, pkg_id, userid, hexkeyid, keyurl, timestamp):
        values = (pkg_id, userid, hexkeyid, keyurl, timestamp)
        self._gpg_confirm = values
        logger.debug('received signal : GPGImport%s' % (repr(values)))

    def on_DownloadStart(self, num_files, num_bytes):
        """Starting a new parallel download batch."""
        #values =  (num_files, num_bytes)
        #print('on_DownloadStart : %s' % (repr(values)))
        self._files_to_download = num_files
        self._files_downloaded = 0
        self.frontend.infobar.set_progress(0.0)
        self.frontend.infobar.info_sub(
            _('Downloading %d files (%sb)...') %
            (num_files, yumex.misc.format_number(num_bytes)))

    def on_DownloadProgress(self, name, frac, total_frac, total_files):
        """Progress for a single element in the batch."""
        #values =  (name, frac, total_frac, total_files)
        #print('on_DownloadProgress : %s' % (repr(values)))
        num = '( %d/%d )' % (self._files_downloaded, self._files_to_download)
        self.frontend.infobar.set_progress(total_frac, label=num)

    def on_DownloadEnd(self, name, status, msg):
        """Download of af single element ended."""
        #values =  (name, status, msg)
        #print('on_DownloadEnd : %s' % (repr(values)))
        if status == -1 or status == 2:  # download OK or already exists
            logger.debug('Downloaded : %s' % name)
            self._files_downloaded += 1
        else:
            logger.debug('Download Error : %s - %s' % (name, msg))

    def on_RepoMetaDataProgress(self, name, frac):
        """Repository Metadata Download progress."""
        values = (name, frac)
        logger.debug('on_RepoMetaDataProgress (root): %s' % (repr(values)))
        if frac == 0.0:
            self.frontend.infobar.info_sub(name)
        else:
            self.frontend.infobar.set_progress(frac)

    def setup(self):
        """Setup the dnf backend daemon."""
        try:
            self.Lock()
            self.SetWatchdogState(False)
            if CONFIG.session.enabled_repos:
                    logger.debug('root: Setting repos : %s' %
                                 CONFIG.session.enabled_repos)
                    self.SetEnabledRepos(CONFIG.session.enabled_repos)
            return True, ''
        except dnfdaemon.client.AccessDeniedError:
            return False, 'not-authorized'
        except dnfdaemon.client.LockedError:
            return False, 'locked-by-other'

    @ExceptionHandler
    def quit(self):
        """Quit the dnf backend daemon."""
        self.Unlock()
        self.Exit()

    @ExceptionHandler
    def reload(self):
        """Reload the dnf backend daemon."""
        self.Unlock()  # Release the lock
        # time.sleep(5)
        self.Lock()  # Load & Lock the daemon
        self.SetWatchdogState(False)
        if CONFIG.session.enabled_repos:
            logger.debug('root: Setting repos : %s' %
                         CONFIG.session.enabled_repos)
            self.SetEnabledRepos(CONFIG.session.enabled_repos)
        self.cache.reset()  # Reset the cache

    def to_pkg_tuple(self, pkg_id):
        """Get package nevra & repoid from an package pkg_id"""
        (n, e, v, r, a, repo_id) = str(pkg_id).split(',')
        return (n, e, v, r, a, repo_id)

    def _make_pkg_object(self, pkgs, flt):
        """Get a list Package objects from a list of pkg_ids & attrs.

        All packages has the same action type.
        Package object are taken from cache if available.

        :param pkgs: list of (pkg_id, summary, size)
        :param flt: pkg_filter (installed, available ....)
        """
        # TODO: should be combined with _make_pkg_object_with_attr
        # No need for 3 almost indentical way to make a list of package objects
        po_list = []
        action = const.FILTER_ACTIONS[flt]
        for pkg_values in pkgs:
            po_list.append(DnfPackage(pkg_values, action, self))
        return self.cache.find_packages(po_list)

    @TimeFunction
    def _make_pkg_object_with_attr(self, pkgs):
        """Make list of Packages from a list of pkg_ids & attrs.

        Package have different action type
        Package object are taken from cache if available.

        :param pkgs: list with (pkg_id, summary, size, action)
        """
        po_list = []
        for elem in pkgs:
            (pkg_id, summary, size, action) = elem
            po_tuple = (pkg_id, summary, size)
            po_list.append(
                DnfPackage(po_tuple, const.BACKEND_ACTIONS[action], self))
        return self.cache.find_packages(po_list)

    def _build_package_list(self, pkg_ids):
        """Make list of Packages from a list of pkg_ids

        Summary, size and action is read from dnf backend

        Package object are taken from cache if available.

        :param pkg_ids:
        """
        # TODO: should be combined with _make_pkg_object_with_attr
        # No need for 3 almost indentical way to make a list of package objects
        po_list = []
        for pkg_id in pkg_ids:
            summary = self.GetAttribute(pkg_id, 'summary')
            size = self.GetAttribute(pkg_id, 'size')
            pkg_values = (pkg_id, summary, size)
            action = const.BACKEND_ACTIONS[self.GetAttribute(pkg_id, 'action')]
            po_list.append(DnfPackage(pkg_values, action, self))
        return self.cache.find_packages(po_list)

    @ExceptionHandler
    @TimeFunction
    def get_packages(self, flt):
        """Get packages for a given pkg filter."""
        if flt == 'all':
            filters = ['installed', 'updates', 'available']
        else:
            filters = [flt]
        result = []
        for pkg_flt in filters:
            # is this type of packages is already cached ?
            if not self.cache.is_populated(pkg_flt):
                fields = ['summary', 'size']  # fields to get
                po_list = self.GetPackages(pkg_flt, fields)
                pkgs = self._make_pkg_object(po_list, pkg_flt)
                self.cache.populate(pkg_flt, pkgs)
            result.extend(yumex.backend.Backend.get_packages(self, pkg_flt))
        return result

    @ExceptionHandler
    def get_downgrades(self, pkg_id):
        """Get downgrades for a given pkg_id"""
        pkgs = self.GetAttribute(pkg_id, 'downgrades')
        return self._build_package_list(pkgs)

    @ExceptionHandler
    def get_repo_ids(self, flt):
        """Get repository ids"""
        repos = self.GetRepositories(flt)
        return repos

    @ExceptionHandler
    def get_repositories(self, flt='*'):
        """Get a list of repo attributes to populate repo view."""
        repo_list = []
        repos = self.GetRepositories(flt)
        for repo_id in repos:
            if repo_id.endswith('-source') or repo_id.endswith('-debuginfo'):
                continue
            repo = self.GetRepo(repo_id)
            repo_list.append([repo['enabled'], repo_id, repo['name'], False])
        return sorted(repo_list, key=lambda elem: elem[1])

    @TimeFunction
    @ExceptionHandler
    def get_packages_by_name(self, name_key, newest_only):
        """Get packages by a given name wildcard.

        :param name_key: package wildcard
        :param newest_only: get lastest version only
        """
        attrs = ['summary', 'size', 'action']
        pkgs = self.GetPackagesByName(name_key, attrs, newest_only)
        return self._make_pkg_object_with_attr(pkgs)

    @ExceptionHandler
    def search(self, search_attrs, keys, match_all, newest_only, tags):
        """Search given pkg attributes for given keys.

        :param search_attrs: package attrs to search in
        :param keys: keys to search for
        :param match_all: match all keys
        """
        attrs = ['summary', 'size', 'action']
        pkgs = self.Search(search_attrs, keys, attrs, match_all,
                           newest_only, tags)
        return self._make_pkg_object_with_attr(pkgs)

    @ExceptionHandler
    def get_groups(self):
        """Get groups/categories from dnf daemon backend"""
        result = self.GetGroups()
        return result

    @TimeFunction
    def get_group_packages(self, grp_id, grp_flt):
        """Get a list of packages from a grp_id and a group filter.

        :param grp_id:
        :param grp_flt:
        """
        attrs = ['summary', 'size', 'action']
        pkgs = self.GetGroupPackages(grp_id, grp_flt, attrs)
        return self._make_pkg_object_with_attr(pkgs)

    def _fullname(self, pkg_id):
        """ Package fullname from a pkg_id """
        (n, e, v, r, a, repo_id) = str(pkg_id).split(',')
        if e and e != '0':
            return '%s-%s:%s-%s.%s (%s)' % (n, e, v, r, a, repo_id)
        else:
            return '%s-%s-%s.%s (%s)' % (n, v, r, a, repo_id)
