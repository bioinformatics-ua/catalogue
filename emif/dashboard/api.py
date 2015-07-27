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
#
from django.http import HttpResponse

from django.contrib.auth.models import User, Group
from django.core.cache import cache

from rest_framework import permissions
from rest_framework import renderers
from rest_framework.authentication import TokenAuthentication

from rest_framework.authentication import SessionAuthentication, BasicAuthentication

from rest_framework.decorators import api_view, parser_classes
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.renderers import JSONRenderer
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated

import os
import mimetypes


from questionnaire.models import Questionnaire, Question

from fingerprint.models import Fingerprint, FingerprintHead, AnswerChange, Answer, FingerprintSubscription
from fingerprint.listings import get_databases_from_solr

from emif.utils import removehs

import datetime

from questionnaire import Processors, QuestionProcessors, Fingerprint_Summary

from django.db.models import Count, Q

from accounts.models import NavigationHistory, RestrictedUserDbs, RestrictedGroup, EmifProfile


from django.conf import settings

from emif.models import City

import json

import urllib2

import random

from hitcount.models import Hit, HitCount
from accounts.models import EmifProfile

from geopy import geocoders

from searchengine.search_indexes import CoreEngine

############################################################
##### Database Types - Web service
############################################################

class DatabaseTypesView(APIView):
    authentication_classes = (SessionAuthentication, BasicAuthentication)
    permission_classes = (IsAuthenticated,)
    def get(self, request, *args, **kw):

        if request.user.is_authenticated():
            db_types = []

            types = Questionnaire.objects.filter(fingerprint__pk__isnull=False).distinct()

            for db in types:
                db_types.append({'id': db.id, 'name': db.name})

            response = Response({'types': db_types}, status=status.HTTP_200_OK)

        else:
            response = Response({}, status=status.HTTP_403_FORBIDDEN)
        return response

############################################################
##### Most Viewed - Web service
############################################################


class MostViewedView(APIView):
    authentication_classes = (SessionAuthentication, BasicAuthentication)
    permission_classes = (IsAuthenticated,)
    def get(self, request, *args, **kw):
        stopwords = ['jerboalistvalues', 'population/comments', 'population/filters', 'population/compare'];
        if request.user.is_authenticated():
            list_viewed = []
            i = 0

            user_history = user_history = NavigationHistory.objects.filter(user=request.user)
            most_viewed = user_history.values('path').annotate(number_viewed=Count('path')).order_by('-number_viewed')

            for viewed in most_viewed:
                if i == 10:
                    break

                if not [stopword for stopword in stopwords if stopword in viewed['path']]:
                    list_viewed.append({'page': viewed['path'], 'count': viewed['number_viewed']})
                    i+=1

            response = Response({'mostviewed': list_viewed}, status=status.HTTP_200_OK)

        else:
            response = Response({}, status=status.HTTP_403_FORBIDDEN)
        return response

############################################################
##### Most Viewed Fingerprint - Web service
############################################################


class MostViewedFingerprintView(APIView):
    authentication_classes = (SessionAuthentication, BasicAuthentication)
    permission_classes = (IsAuthenticated,)
    def get(self, request, *args, **kw):

        if request.user.is_authenticated():
            list_viewed = []

            try:
                eprofile = EmifProfile.objects.get(user=request.user)
            except EmifProfile.DoesNotExist:
                print "-- ERROR: Couldn't get emif profile for user"

            most_hit = Hit.objects.filter(user=request.user).values('user','hitcount__object_pk').annotate(total_hits=Count('hitcount')).order_by('-total_hits')

            i=0

            for hit in most_hit:
                try:
                    this_fingerprint = Fingerprint.valid().get(id=hit['hitcount__object_pk'])

                    if eprofile.restricted:
                        try:
                            allowed = RestrictedUserDbs.objects.get(user=request.user, fingerprint=this_fingerprint)
                        except RestrictedUserDbs.DoesNotExist:
                            restricted = RestrictedGroup.hashes(request.user)

                            if this_fingerprint.fingerprint_hash not in RestrictedGroup.hashes(request.user):
                                continue

                    list_viewed.append(
                        {
                            'hash': this_fingerprint.fingerprint_hash,
                            'name': this_fingerprint.findName(),
                            'count': hit['total_hits']
                        })
                    i+=1
                    if i == 10:
                        break

                except Fingerprint.DoesNotExist:
                    print "-- Error on hitcount for fingerprint with id "+hit['hitcount__object_pk']

            response = Response({'mostviewed': list_viewed}, status=status.HTTP_200_OK)

        else:
            response = Response({}, status=status.HTTP_403_FORBIDDEN)
        return response

############################################################
##### Last Users - Web service
############################################################


class LastUsersView(APIView):
    authentication_classes = (SessionAuthentication, BasicAuthentication)
    permission_classes = (IsAuthenticated,)
    def get(self, request, *args, **kw):

        if request.user.is_authenticated() and request.user.is_staff == True:
            last_users = []

            users = User.objects.all().order_by('-last_login')[:10]

            for user in users:
                last_users.append({'user': user.get_full_name(), 'last_login': user.last_login.strftime("%Y-%m-%d %H:%M:%S")})

            response = Response({'lastusers': last_users}, status=status.HTTP_200_OK)

        else:
            response = Response({}, status=status.HTTP_403_FORBIDDEN)
        return response

############################################################
##### Top Users - Web service
############################################################


class TopUsersView(APIView):
    authentication_classes = (SessionAuthentication, BasicAuthentication)
    permission_classes = (IsAuthenticated,)
    def get(self, request, *args, **kw):

        if request.user.is_authenticated() and request.user.is_staff == True:

            top_users = EmifProfile.top_users(limit=10, days_to_count=30)

            response = Response({'topusers': top_users}, status=status.HTTP_200_OK)

        else:
            response = Response({}, status=status.HTTP_403_FORBIDDEN)
        return response

############################################################
##### Top Navigators - Web service
############################################################


class TopNavigatorsView(APIView):
    authentication_classes = (SessionAuthentication, BasicAuthentication)
    permission_classes = (IsAuthenticated,)
    def get(self, request, *args, **kw):

        if request.user.is_authenticated() and request.user.is_staff == True:

            top_users = EmifProfile.top_navigators(limit=10, days_to_count=30)

            response = Response({'topnavigators': top_users}, status=status.HTTP_200_OK)

        else:
            response = Response({}, status=status.HTTP_403_FORBIDDEN)
        return response

############################################################
##### User Statistics - Web service
############################################################


class UserStatsView(APIView):
    authentication_classes = (SessionAuthentication, BasicAuthentication)
    permission_classes = (IsAuthenticated,)
    def get(self, request, *args, **kw):

        if request.user.is_authenticated():
            stats = {}

            # statistics about the user
            # number of databases as owner
            # number of dbs as a shared user
            # most popular database of this user(with most unique views)
            # main database type

            stats['lastlogin'] = request.user.last_login.strftime("%Y-%m-%d %H:%M:%S")

            my_db = Fingerprint.objects.filter(owner=request.user).order_by('-hits')
            my_db_share = Fingerprint.objects.filter(shared=request.user)

            stats['numberownerdb'] = my_db.count()
            stats['numbershareddb'] = my_db_share.count()

            mostpopular = None
            try:
                mostpopular = my_db[0]
            except:
                # no database owned
                pass

            if mostpopular == None:
                stats['mostpopulardb'] = {'name': '---', 'hash': '---', 'hits': '---'}
            else:
                stats['mostpopulardb'] = {
                                    'name': mostpopular.findName(),
                                    'hash': mostpopular.fingerprint_hash,
                                    'hits': mostpopular.hits}

            all_dbs = my_db | my_db_share

            quest_types = all_dbs.order_by('questionnaire').values('questionnaire__name').annotate(Count('questionnaire')).order_by('-questionnaire__count')

            try:
                stats['populartype'] = quest_types[0]['questionnaire__name']
            except:
                stats['populartype'] = "---"

            response = Response({'stats': stats}, status=status.HTTP_200_OK)

        else:
            response = Response({}, status=status.HTTP_403_FORBIDDEN)
        return response


############################################################
##### Feed - Web service
############################################################


class FeedView(APIView):
    authentication_classes = (SessionAuthentication, BasicAuthentication)
    permission_classes = (IsAuthenticated,)
    def get(self, request, *args, **kw):

        if request.user.is_authenticated():

            # get from subscriptions too
            subs = FingerprintSubscription.objects.filter(user=request.user, removed=False).values_list('fingerprint__id', flat=True)

            modifications = FingerprintHead.objects.filter(
                (
                Q(fingerprint_id__id__in=subs)
                | Q(fingerprint_id__owner=request.user)
                | Q(fingerprint_id__shared=request.user)
                ),
                fingerprint_id__removed = False).distinct().order_by("-date")

            feed = []

            modifications = modifications[:30]

            aggregate = []
            previous = None

            hash = "feed_agg"

            for mod in modifications:
                hash+=str(mod.id)+"_"

            feed = cache.get(hash)

            if feed == None:
                feed = []
                for mod in modifications:

                    if previous != None and mod.fingerprint_id != previous.fingerprint_id and len(aggregate) != 0:
                        feed.append(aggregate)
                        aggregate = []

                    alterations = []

                    anschg = AnswerChange.objects.filter(revision_head = mod)


                    for chg in anschg:

                        question = chg.answer.question

                        try:
                            old_value = Fingerprint_Summary[question.type](chg.old_value)
                            new_value = Fingerprint_Summary[question.type](chg.new_value)
                        except:
                            old_value = chg.old_value
                            new_value = chg.new_value

                        def noneIsEmpty(value):
                            if value == None:
                                return ""

                            return value

                        alterations.append({
                                'number': question.number,
                                'text': removehs(question.text),
                                'oldvalue': noneIsEmpty(old_value),
                                'newvalue': noneIsEmpty(new_value),
                                'oldcomment': noneIsEmpty(chg.old_comment),
                                'newcomment': noneIsEmpty(chg.new_comment)
                            })

                    icon = 'edit'

                    if(mod.revision == 1):
                        icon = 'add'

                    aggregate.append({
                        'hash': mod.fingerprint_id.fingerprint_hash,
                        'name': mod.fingerprint_id.findName(),
                        'date': mod.date.strftime("%Y-%m-%d %H:%M"),
                        'icon': icon,
                        'alterations': alterations,
                        'revision': mod.revision
                    })

                    previous = mod

                feed.append(aggregate)

                cache.set(hash, feed, 14400)

            response = Response({'hasfeed': True, 'feed': feed }, status=status.HTTP_200_OK)

        else:
            response = Response({}, status=status.HTTP_403_FORBIDDEN)
        return response

############################################################
##### Tag Cloud - Web service
############################################################


class TagCloudView(APIView):
    authentication_classes = (SessionAuthentication, BasicAuthentication)
    permission_classes = (IsAuthenticated,)
    def get(self, request, *args, **kw):

        if request.user.is_authenticated():

            tags = []

            solrlink = 'http://' +settings.SOLR_HOST+ ':'+ settings.SOLR_PORT+settings.SOLR_PATH+'/admin/luke?fl=text_t&numTerms=300&wt=json'


            stopwords = cache.get('tagcloud_stopwords')

            if stopwords == None:
                module_dir = os.path.dirname(__file__)  # get current directory
                file_path = os.path.join(module_dir, 'stopwords.txt')

                stopwords = []
                with open(file_path, 'r') as stopword_list:
                    list = stopword_list.read().split('\n')


                    for elem in list:
                        clean = elem.strip().lower()
                        if len(clean)  > 0:
                            stopwords.append(clean)

                cache.set('tagcloud_stopwords', stopwords, 1440) # 24 hours of cache

            topwords = json.load(urllib2.urlopen(solrlink))['fields']['text_t']['topTerms']

            i = 0

            while i < len(topwords):
                if len(topwords[i]) > 2 and topwords[i] not in stopwords:
                    tags.append({
                        'name': topwords[i],
                        'relevance': topwords[i+1],
                        'link': 'resultsdiff/1'
                    })

                if len(tags) >= 20:
                    break

                i+=2

            random.shuffle(tags, random.random)


            response = Response({'tags': tags}, status=status.HTTP_200_OK)

        else:
            response = Response({}, status=status.HTTP_403_FORBIDDEN)
        return response


############################################################
##### Vector Map - Web service
############################################################

class VectorMapView(APIView):
    authentication_classes = (SessionAuthentication, BasicAuthentication)
    permission_classes = (IsAuthenticated,)

    # GET
    def get(self, request, *args, **kw):

        if request.user.is_authenticated():

            query = None
            isAdvanced = False
            if(request.session.get('isAdvanced') == True):
                query = request.session.get('query')
                if query == None:
                    query = "*:*"

                isAdvanced = True
            else:
                if(request.session.get('query') != None):
                    query = "'"+re.sub("['\"']","\\'",request.session.get('query'))+"'"
                    query = "text_t:"+query

                else:
                    query = "*:*"

            #print "query@" + query
            list_databases = get_databases_from_solr(request, query)

            list_locations = []
            _long_lats = []
            # since the geolocation is now adding the locations, we no longer need to look it up when showing,
            # we rather get it directly
            db_list = {}
            questionnaires_ids = {}
            qqs = Questionnaire.objects.all()

            for q in qqs:
                questionnaires_ids[q.slug] = (q.pk, q.name)
            for database in list_databases:

                if database.location.find(".")!= -1:
                    _loc = database.location.split(".")[0]
                else:
                    _loc = database.location

                city=None
                g = geocoders.GeoNames(username='bastiao')

                if _loc!= None and g != None and len(_loc)>1:
                    try:
                        city = City.objects.filter(name=_loc.lower())[0]

                    # if dont have this city on the db
                    except:
                        print "-- Error: The city " + _loc + " doesnt exist on the database. Maybe too much requests were being made when it happened ? Trying again..."

                        #obtain lat and longitude
                        city = retrieve_geolocation(_loc.lower())

                        if city != None:
                            #print city

                            city.save()

                        else:
                            print "-- Error: retrieving geolocation"
                            continue

                    _long_lats.append(str(city.lat) + ", " + str(city.long))

                    import pdb
                    #pdb.set_trace()
                    def __cleanvalue(v):
                        return v.encode('ascii', 'ignore').strip().replace('\n', ' ').replace('\r', ' ')

                    def db_ready(database, city):
                        return {    'name': database.name,
                                    'location': __cleanvalue(database.location),
                                    'institution': __cleanvalue(database.institution),
                                    'contact': __cleanvalue(database.email_contact),
                                    'number_patients': __cleanvalue(database.number_patients),
                                    'ttype': __cleanvalue(database.type_name),
                                    'id' : database.id,
                                    'admin_name': __cleanvalue(database.admin_name),
                                    'admin_address': __cleanvalue(database.admin_address),
                                    'admin_email': __cleanvalue(database.admin_email),
                                    'admin_phone': __cleanvalue(database.admin_phone),
                                    'scien_name': __cleanvalue(database.scien_name),
                                    'scien_address': __cleanvalue(database.scien_address),
                                    'scien_email': __cleanvalue(database.scien_email),
                                    'scien_phone': __cleanvalue(database.scien_phone),
                                    'tec_name': __cleanvalue(database.tec_name),
                                    'tec_address': __cleanvalue(database.tec_address),
                                    'tec_email': __cleanvalue(database.tec_email),
                                    'tec_phone': __cleanvalue(database.tec_phone),
                                    'lat' : str(city.lat),
                                    'long': str(city.long),
                                }

                    if((city.lat, city.long) in db_list):
                        db_list[(city.lat, city.long)].append(db_ready(database, city))
                    else:
                        db_list[(city.lat, city.long)] = [db_ready(database, city)]
                list_locations.append(_loc)

            # pass information on the Response ('tags')
            response = Response(
            {'markers': _long_lats,
            'locations': list_locations},
            status=status.HTTP_200_OK)
        else:
            response = Response({}, status=status.HTTP_403_FORBIDDEN)
        return response

############################################################
##### Recommendations based on Subscriptions and More Like This - Web service
############################################################


class RecommendationsView(APIView):
    authentication_classes = (SessionAuthentication, BasicAuthentication)
    permission_classes = (IsAuthenticated,)

    __subscribed = []
    __mlt_fused = {}

    def get(self, request, *args, **kw):
        self.__subscribed = []
        self.__mlt_fused = {}

        if request.user.is_authenticated():

            ordered = cache.get('recommendations_'+str(request.user.id))

            if ordered == None:
                maxx = 100
                subscriptions = FingerprintSubscription.active().filter(user=request.user)

                # first we generate the list of already subscribed databases, since they wont appear on suggestions
                for subscription in subscriptions:
                    self.__subscribed.append(subscription.fingerprint.fingerprint_hash)

                c = CoreEngine()
                for subscription in subscriptions:
                    fingerprint = subscription.fingerprint
                    this_mlt = c.more_like_this(fingerprint.fingerprint_hash, fingerprint.questionnaire.slug, maxx=maxx)

                    self.__merge(this_mlt)

                ordered = sorted(self.__mlt_fused.values(), reverse=True, key=lambda x:x['score'])[:10]

                for entry in ordered:
                    try:
                        fingerprint = Fingerprint.valid().get(fingerprint_hash=entry['id'])
                    except Fingerprint.DoesNotExist:
                        continue

                    entry['name'] = fingerprint.findName()

                    entry['href'] = 'fingerprint/'+fingerprint.fingerprint_hash+'/1/'

                cache.set('recommendations_'+str(request.user.id), ordered, 720)


            response = Response({'mlt': ordered}, status=status.HTTP_200_OK)

        else:
            response = Response({}, status=status.HTTP_403_FORBIDDEN)

        return response

    def __merge(self, merging):

        for db in merging:
            if db['id'] not in self.__subscribed:
                if db['id'] in self.__mlt_fused:
                    current = self.__mlt_fused[db['id']]

                    current['score'] += db['score']

                    self.__mlt_fused[db['id']] = current
                else:
                    self.__mlt_fused[db['id']] = db
