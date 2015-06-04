# -*- coding: utf-8 -*-
# Copyright (C) 2014 Universidade de Aveiro, DETI/IEETA, Bioinformatics Group - http://bioinformatics.ua.pt/
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
from django.db import models
from django.contrib.auth.models import User
import os

from django.db.models import Max
from django_resized import ResizedImageField

from django.conf import settings

def iconHash(instance, filename):
    ''' Callable to be called by the ImageField, this renames the file to the generic hash
        so we avoid collisions
    '''
    return '.{0}icons/{1}'.format(settings.MEDIA_URL, instance.slug)

# There are three types of plugins:
class Plugin(models.Model):
    GLOBAL      = 0
    DATABASE    = 1
    THIRD_PARTY = 2
    FULL_FLEDGED= 3

    TYPES = [
                (GLOBAL,        'Global plugin, for the main dashboard'),
                (DATABASE,      'Database related plugin, for the database view'),
                (FULL_FLEDGED,  'Full-fledged application widget'),
                (THIRD_PARTY,   'Third party full-fledged applications')
            ]

    name = models.CharField(max_length=100)
    slug = models.CharField(max_length=100, unique=True)
    type = models.IntegerField(choices=TYPES, default=GLOBAL)
    owner= models.ForeignKey(User)
    icon = ResizedImageField(size=[200, 200], upload_to=iconHash, null=True)
    create_date     = models.DateTimeField(auto_now_add=True)
    latest_update   = models.DateTimeField(auto_now=True)

    removed = models.BooleanField(default=False)

    def create_date_repr(self):
        return self.create_date.strftime("%Y-%m-%d %H:%M:%S")

    def latest_update_repr(self):
        return self.latest_update.strftime("%Y-%m-%d %H:%M:%S")

    def type_repr(self):
        try:
            return dict(self.TYPES)[self.type]
        except KeyError:
            return "TYPE ERROR"

    @staticmethod
    def __generateSlug(name):
        return os.urandom(16).encode('hex');

    @staticmethod
    def create(name, type, owner, icon):
        slug = Plugin.__generateSlug(name)
        if(icon != None):
            p = Plugin(name=name, type=type, slug=slug, owner=owner, icon=icon)
        else:
            p = Plugin(name=name, type=type, slug=slug, owner=owner)
        p.save()

        return p

    @staticmethod
    def update(slug, name, type, owner, icon):

        try:
            p = Plugin.objects.get(slug=slug)

            p.name=name
            p.type=type
            p.owner=owner

            if icon != None:
                p.icon = icon

            p.save()

            return p

        except Plugin.DoesNotExist:
            pass

        return None

    @staticmethod
    def all(owner=None):
        tmp = Plugin.objects.filter(removed = False)

        if owner != None:
            tmp = tmp.filter(owner=owner)

        return tmp

    # gets the file from the filesystem
    def getLatest(self):
        try:
            return self.versions().filter(approved=True)[:1][0]
        except PluginVersion.DoesNotExist:
            return None

    def versions(self):
        return PluginVersion.all(plugin=self)

    @staticmethod
    def remove(slug):
        try:
            plugin = Plugin.objects.get(slug=slug)

            plugin.removed = True
            plugin.save()

            return True

        except Plugin.DoesNotExist:
            print "-- Error: Retrieving plugin"

        return False

    def __str__(self):
        if self.name != None:
            return self.name

        return Undefined

    class Meta:
        ordering = ['-latest_update']

class PluginVersion(models.Model):
    plugin      = models.ForeignKey(Plugin)
    is_remote   = models.BooleanField(default=False)
    path        = models.TextField()
    version     = models.IntegerField()

    approved    = models.BooleanField(default=False)
    submitted   = models.BooleanField(default=False)
    submitted_desc = models.TextField(null=True)
    create_date     = models.DateTimeField(auto_now_add=True)
    latest_update   = models.DateTimeField(auto_now=True)

    removed     = models.BooleanField(default=False)

    @staticmethod
    def all(plugin=None, approved=None):
        tmp = PluginVersion.objects.filter(removed=False)

        if plugin != None:
            tmp = tmp.filter(plugin=plugin)

        if approved != None:
            tmp = tmp.filter(approved=True)

        return tmp

    @staticmethod
    def create(plugin_hash, version, is_remote, data):
        pv = None
        p = Plugin.objects.get(slug=plugin_hash)

        pv = PluginVersion(plugin = p, is_remote = is_remote,
            path = data, version = version)

        pv.save()

        return pv

    @staticmethod
    def submit(plugin_hash, version, desc):
        from developer.tasks import sendCommitEmails

        pv  = None
        p   = Plugin.objects.get(slug=plugin_hash)

        try:
            pv = PluginVersion.all(plugin=p).get(version=version)

            pv.submitted = True
            pv.approved = False
            pv.submitted_desc = desc

            sendCommitEmails.apply_async([p, pv])

            pv.save()

        except PluginVersion.DoesNotExist:
            pass

        return pv

    @staticmethod
    def update(plugin_hash, version_old, version_new, is_remote, data):
        pv = None
        p = Plugin.objects.get(slug=plugin_hash)
        try:
            pv = PluginVersion.all(plugin=p).get(version=version_old)

            pv.version = version_new
            pv.is_remote = is_remote
            pv.path = data

            pv.submitted = False
            pv.approved = False

            pv.save()

        except PluginVersion.DoesNotExist:
            pass

        return pv

    def __str__(self):
        return '%s : v.%r' % (self.plugin.name, self.version)

    def create_date_repr(self):
        return self.create_date.strftime("%Y-%m-%d %H:%M:%S")

    def latest_update_repr(self):
        return self.latest_update.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def all_valid(type=None):
        all = None

        all = PluginVersion.all(approved=True).order_by('plugin__id', '-version').distinct('plugin__id')

        if type != None:
            all = all.filter(plugin__type=type)

        return all


    class Meta:
        ordering = ['-version']
        verbose_name_plural = "Plugin versions waiting for approval"


# Upload dependencies
class VersionDep(models.Model):
    pluginversion = models.ForeignKey(PluginVersion)
    created_date = models.DateTimeField(auto_now_add=True)
    latest_date = models.DateTimeField(auto_now=True)
    revision = models.CharField(max_length=255)
    path = models.CharField(max_length=255)
    filename = models.CharField(max_length=255)
    size = models.FloatField(default=0)
    removed = models.BooleanField()

    class Meta:
        ordering = ['-latest_date']

    @staticmethod
    def all(version=None):
        tmp = VersionDep.objects.filter(removed=False)

        if version != None:
            tmp = tmp.filter(pluginversion=version)

        return tmp

    @staticmethod
    def unique(version=None):
        version_deps = VersionDep.all(version=version)

        deps = version_deps.values('filename').annotate(latest=Max('latest_date'))
        uniquedeps = []
        for file in deps:
            uniquedeps.append(version_deps.get(filename = file['filename'], latest_date = file['latest']))

        return uniquedeps
