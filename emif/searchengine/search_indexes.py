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
"""A module for Python index

.. moduleauthor:: Luís A. Bastião Silva <bastiao@ua.pt>
"""

from __future__ import print_function
import pysolr

from django.db.models.signals import post_save
from django.dispatch import receiver

from questionnaire.models import *
from searchengine.models import Slugs

from django.db.models.signals import post_save
from django.dispatch import receiver

import logging
import ast

import md5
import random

from django.conf import settings


from django.template.defaultfilters import slugify

import datetime

from questionnaire.models import Questionnaire, QuestionSet

import re

logger = logging.getLogger()

def generate_hash():
    hash = md5.new()
    hash.update("".join(map(lambda i: chr(random.randint(0, 255)), range(16))))
    hash.update(settings.SECRET_KEY)
    key = hash.hexdigest()
    return key

class CoreEngine:
    """It is responsible for index the documents and search over them
    It also connects to SOLR
    """

    CONNECTION_TIMEOUT_DEFAULT = 10
    def __init__(self, timeout=CONNECTION_TIMEOUT_DEFAULT, core='collection1'):
        # Setup a Solr instance. The timeout is optional.
        self.solr = pysolr.Solr('http://' +settings.SOLR_HOST+ ':'+ settings.SOLR_PORT+settings.SOLR_PATH+'/'+core, timeout=timeout)


    def reindex_quest_solr(self):
        p = re.compile("(\\d{1,2})(\.\\d{2})*$", re.L)

        #qsets = QuestionSet.objects.all()
        slugs = []
        questionaires = Questionnaire.objects.filter(disable=False)

        solr = pysolr.Solr('http://' +settings.SOLR_HOST+ ':'+ settings.SOLR_PORT+settings.SOLR_PATH)
        start=0
        rows=100
        fl=''

        for quest in questionaires:
            id = quest.id
            obj = {"id":"questionaire_"+str(id)}
            qsets = QuestionSet.objects.filter(questionnaire=quest)
            for qs in qsets:
                #print qs
                questions = qs.questions()
                for q in questions:
                    x = q.slug_fk
                    key = str(x.slug1) + "_qs"
                    obj[key] = q.text
            slugs.append(obj)


        for quest in questionaires:
            solr.delete(id='questionaire_'+str(id))

        solr.add(slugs)

        print ("QUITTING")

    def index_fingerprint(self, doc):
        """Index fingerprint
        """
        # index document
        self.index_fingerprint_as_json(doc)


    def index_fingerprints(self, docs):
        """Index fingerprint
        """
        # index document
        self.index_fingerprint_as_json(docs, several = True)

    def index_fingerprint_as_json(self, d, several=False):
        """Index fingerprint as json
        """
        # index document
        xml_answer = None
        if several:
            xml_answer = self.solr.add(d)
        else:
            xml_answer = self.solr.add([d])

        self.optimize()

    def optimize(self):
        """This function optimize the index. It improvement the search and retrieve documents subprocess.
        However, it is a hard tasks, and call it for every index document might not be a good idea.
        """
        self.solr.optimize()

    def update(self, doc):
        """Update the document
        """
        # Search  and identify the document id

        self.solr.add([doc])


    def delete(self, id_doc):


        """Delete the document
        """
        self.solr.delete(id=id_doc)

    def deleteQuery(self, q):
        """Delete the document
        """
        self.solr.delete(q=q)

    def search_fingerprint(self, query, start=0, rows=100, fl='', sort='', facet="off"):
        """search the fingerprint
        """
        # Later, searching is easy. In the simple case, just a plain Lucene-style
        # query is fine.
        results = self.solr.search(query,**{
                'facet': facet,
                'rows': rows,
                'start': start,
                'fl': fl,
                'sort': sort
                })
        return results

    def search_highlight(self, query, start=0, rows=100, fl='', sort='', hlfl=""):
        """search the fingerprint
        """
        #hl=true&hl.fl=text_t

        print ("HIGHLIGHT WAY:")
        print (hlfl)
        print ("--")

        results = self.solr.search(query,**{
                'rows': rows,
                'start': start,
                'fl': fl,
                'sort': sort,
                'hl':"true",
                'hl.fl': hlfl, "hl.fragsize":0
                })
        return results

    def highlight_questions(self, query, start=0, rows=1000, fl='id', sort='', hlfl="*"):
        """search the fingerprint
        """
        #hl=true&hl.fl=text_t
        query = "qs_all:"+query
        print(query)
        results = self.solr.search(query,**{
                'rows': rows,
                'start': start,
                'fl': fl,
                'sort': sort,
                'hl':"true",
                'hl.fl': hlfl
                })
        return results

    def more_like_this(self, id_doc, type, start=0, fl='id, score', maxx=100):
        similar = self.solr.more_like_this(q='id:'+id_doc, fq='type_t:'+type, start=start, rows=maxx, mltcount=maxx, mltfl='mlt_t', mltmintf=2, mltmindf=2, mltminwl=4, fl=fl)
        return similar


def convert_text_to_slug_old(text):
    #TODO: optimize
    text_aux = text.replace(' ', '_').replace('?','').replace('.', '').replace(',','')
    if text_aux[:-1] == '_':
        text_aux = text_aux[:-1]
    return text_aux

def convert_text_to_slug(text):
    return slugify(text)

def clean_answer(answer):
    #TODO: optimize
    return answer


def get_slug_from_choice(v, q):
    choice = Choice.objects.filter(question=q).filter(value=v)
    if (len(choice)>0):
        print(choice[0].text)
        print(choice[0].value)



def index_answeres_from_qvalues(qvalues, questionnaire, subject, fingerprint_id, extra_fields=None, created_date=None):

    c = CoreEngine()
    d = {}

    # print("Indexing...")
    results = c.search_fingerprint("id:"+fingerprint_id)
    if (len(results)>0):
        d = results.docs[0]

    text = ""
    ''' For god sake, i dont understand what this was doing here, since its not being used
     slugs_objs = Slugs.objects.all()
    slugs = []
    for s in slugs_objs:
        slugs.append(s.description)
    '''
    appending_text = ""
    #slugs_objs = None
    now = datetime.datetime.now()

    for qs_aux, qlist in qvalues:
        for question, qdict in qlist:

            #print(question.slug_fk.slug1)

            try:
                choices = None
                value = None
                choices_txt = None
                if qdict.has_key('value'):
                    value = qdict['value']

                    if "yes" in qdict['value']:
                        appending_text += question.text

                elif qdict.has_key('choices'):
                    #import pdb
                    #pdb.set_trace()
                    choices = qdict['choices']
                    qv = ""
                    try:
                        qv = qdict['qvalue']

                    except:
                        # raise
                        pass

                    value = qv

                    do_again = False
                    try:
                        if len(choices[0])==3:
                            for choice, unk, checked  in choices:
                                if checked == " checked":
                                    value = value + "#" + choice.value

                        elif len(choices[0])==4:
                            for choice, unk, checked, _aux  in choices:
                                if checked == " checked":
                                    if _aux != "":
                                        value = value + "#" + choice.value + "{" + _aux +"}"
                                    else:
                                        value = value + "#" + choice.value


                        elif len(choices[0])==2:
                            for checked, choice  in choices:
                                # print("checked" + str(checked))
                                if checked:
                                    value = value + "#" + choice.value

                    except:
                        do_again = True

                    if do_again:
                        for checked, choice  in choices:
                            # print("checked" + str(checked))
                            if checked:

                                value = value + "#" + choice.value


                    # print("choice value " + value)

                    '''
                    TO-DO
                    Verify if symbols || (separator) is compatible with solr
                    '''
                    #Save in case of extra field is filled
                    if qdict.has_key('extras'):
                        extras = qdict['extras']
                        # print("EXTRAS: " + str(extras))
                        for q, val in extras:
                            # print("VAL: " + str(q) + " - " + str(val))
                            if val:
                                value = value + "||" + val


                else:
                    #print("continue")
                    pass


                # print(value)
                slug = question.slug_fk.slug1
                #slug = question.slug
                # slug_aux = ""
                # if len(slug)>2:
                #     slug = question.slug
                # else:
                #     slug = convert_text_to_slug(question.text)
                #slug_final = slug+"_t"

                #results = Slugs.objects.filter(description=question.text)

                #if slugs_dict==None or len(results)==0:
                # if question.text not in slugs:
                #     slugsAux = Slugs()
                #     slugsAux.slug1 = slug_final
                #     slugsAux.description = question.text
                #     slugsAux.question = question
                #     slugsAux.save()

                setProperFields(d, question, slug, value)
                #print(d)

                #d[slug_final] = value
                if value!=None:
                    text += value + " "
            except:
                # raise
                pass


    d['id']=fingerprint_id

    d['type_t']=questionnaire.name.replace(" ", "").lower()
    if created_date==None:
        d['created_t']= now.strftime('%Y-%m-%d %H:%M:%S.%f')
    else:
        d['created_t'] = created_date
    d['date_last_modification_t']= now.strftime('%Y-%m-%d %H:%M:%S.%f')

    # We dont want to reset share's... only set field if there isnt already one

    if d.get('user_t') == None:
        d['user_t']= subject
    # since its now by parts, we have absolutely no idea what was already there and what is new,
    # to this must be done again from scratch
    d['text_t']= generateFreeText(d)
    d['mlt_t'] = generateMltText(d)

    if extra_fields!=None:
        d = dict(d.items() + extra_fields.items())

    #print(d)

    # We only delete right before adding, so we dont lose what is on the database
    # in case anything fails on the process above
    if(len(results) > 0):
        c.delete(results.docs[0]['id'])
        del d['_version_']

    c.index_fingerprint_as_json(d)

# Set all proper fields for this question (this has in attention question types and such)
# P.e., for dates, it will date *_t and *_dt and for numeric *_t and *_d
def setProperFields(d, question, field, value):

    # We always set the text one
    #print (field+"_t" + " = "+value)
    d[field+"_t"] = value


    # Check and also apply the correct type, if any
    suffix = assert_suffix(str(question.type))
    if suffix != None:
        val = convert_value(value, str(question.type))
        if val != None:
            d[field+suffix] = val

    return d

def assert_suffix(type):
    if type.lower() == "numeric":
        return "_d"
    elif type.lower() == "datepicker":
        return "_dt"
    # else
    return None

def convertDate(value):
    value = re.sub("\"", "", value)

    try:
        # First we try converting to normalized format, yyyy-mm-dd
        date = datetime.datetime.strptime(value, '%Y-%m-%d')
        return date
    except ValueError:
        #print('failed 1')
        pass

    try:
        # We try yyyy/mm/dd
        date = datetime.datetime.strptime(value, '%Y/%m/%d')
        return date
    except ValueError:
        #print('failed 2')
        pass

    try:
        # We try just the year, yyyy
        date = datetime.datetime.strptime(value, '%Y')
        return date
    except ValueError:
        #print('failed 3')
        pass

    # failed conversion
    return None

def replaceDate(m):
    group = m.group(0)

    converted_date = convertDate(group)
    if converted_date == None:
        return '*'
    return converted_date.isoformat()+'T00:00:00Z'

def convert_value(value, type, search=False):

    if type == "numeric":
        #print("type numeric")
        try:
            # remove separators if they exist on representation
            value = re.sub("[^0-9.,]", "", value)
            #print ("value:"+value)
            # replace usual mistake , to .
            value = re.sub("[,]", ".", value)
            value = float(value)
            return value
        except ValueError:
            pass

    elif type == "datepicker":
        if (value.startswith('[') and value.endswith(']')):
            temp = value
            temp = re.sub("[0-9/-]+", replaceDate, temp)

            return temp
        else:
            # for some weird reason, single date queries to solr returns error,
            # they must be in a range format always ? wth i just do a range query on the same date
            result = convertDate(value)
            if (result != None):
                result = result.isoformat()
                if search:
                    return "["+result+"T00:00:00Z TO "+result+"T23:59:59Z]"
                else:
                    return result+"T00:00:00Z"

    return None

# Generates the freetext field, from current parameters
def generateFreeText(d):
    freetext = ''
    dont_index = ['text_t', 'created_t','date_last_modification_t','type_t', 'user_t', 'mlt_t']

    for q in d:
        if(q.endswith('_t') and q not in dont_index and d[q] != None and len(d[q]) > 0):
            freetext += (re.sub('[#_{}]',' ', d[q]) + ' ')

    return freetext.strip()

# Generates the mlt field, from current parameters
def generateMltText(d):
    freetext = ''
    dont_index = ['text_t', 'created_t','date_last_modification_t','type_t', 'user_t', 'database_name_t', 'mlt_t']

    try:
        quest = Questionnaire.objects.get(slug=d['type_t'])
        questions = Question.objects.filter(questionset__questionnaire=quest, mlt_ignore=True)

        for question in questions:
            dont_index.append(question.slug_fk.slug1+'_t')

    except Questionnaire.DoesNotExist:
        print("-- Error retrieving questionnaire ignore mlt slugs")

    for q in d:
        if(q.endswith('_t') and not q.startswith('comment_') and q not in dont_index and d[q] != None and len(d[q]) > 0):
            freetext += (re.sub('[#_{}]',' ', d[q]) + ' ')

    return freetext.strip()
