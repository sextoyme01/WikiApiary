"""Record extension data."""
# pylint: disable=C0301,W1201

from apiary.tasks import BaseApiaryTask
import requests
import logging
import HTMLParser
import re
import semantic_version


LOGGER = logging.getLogger()

class RecordExtensionsTask(BaseApiaryTask):

    def run(self, site_id, sitename, api_url):
        """Get extensions from the website and write them to WikiApiary."""

        LOGGER.info("Retrieve record_extensions for %d", site_id)

        data_url = api_url + '?action=query&meta=siteinfo&siprop=extensions&format=json'

        LOGGER.debug("Requesting from %s" % data_url)
        try:
            req = requests.get(data_url, timeout = 15, verify=False)
            data = req.json()
        except Exception, e:
            LOGGER.error(e)
            raise Exception(e)

        if req.status_code == 200:
            # Successfully pulled data
            if 'query' in data:
                # Looks like a valid response
                template_block = self.generate_template(data['query']['extensions'])
                wiki_return = self.bumble_bee.call({
                    'action': 'edit',
                    'title': "%s/Extensions" % sitename,
                    'text': template_block,
                    'token': self.bumble_bee_token,
                    'bot': 'true'
                    })
                LOGGER.debug(wiki_return)

                if 'error' in wiki_return:
                    raise Exception(wiki_return)

                return wiki_return
            else:
                self.record_error(
                    site_id=site_id,
                    sitename=sitename,
                    log_message='Returned unexpected JSON when requesting extension data.',
                    log_type='warn',
                    log_severity='normal',
                    log_bot='Bumble Bee',
                    log_url=data_url
                )
                raise Exception('Returned unexpected JSON when requesting extension data.')
                

    def generate_template(self, ext_obj):
        """Build a the wikitext for the extensions subpage."""

        h = HTMLParser.HTMLParser()

        # Some keys we do not want to store in WikiApiary
        ignore_keys = ['descriptionmsg']
        # Some keys we turn into more readable names for using inside of WikiApiary
        key_names = {
            'author': 'Extension author',
            'name': 'Extension name',
            'version': 'Extension version',
            'type': 'Extension type',
            'url': 'Extension URL'
        }

        template_block = "<noinclude>{{Extensions subpage}}</noinclude><includeonly>"

        for extension in ext_obj:
            if 'name' in extension:
                template_block += "{{Extension in use\n"

                for item in extension:
                    if item not in ignore_keys:

                        name = key_names.get(item, item)
                        value = extension[item]

                        if item == 'name':
                            # Sometimes people make the name of the extension a hyperlink using
                            # wikitext links and this makes things ugly. So, let's detect that if present.
                            if re.match(r'\[(http[^\s]+)\s+([^\]]+)\]', value):
                                (possible_url, value) = re.findall(r'\[(http[^\s]+)\s+([^\]]+)\]', value)[0]
                                # If a URL was given in the name, and not given as a formal part of the
                                # extension definition (yes, this happens) then add this to the template
                                # it is up to the template to decide what to do with this
                                template_block += "|URL Embedded in name=%s" % possible_url

                            value = self.filter_illegal_chars(value)
                            # Before unescaping 'regular' unicode characters, first deal with spaces
                            # because they cause problems when converted to unicode non-breaking spaces
                            value = value.replace('&nbsp;', ' ').replace('&#160;', ' ').replace('&160;', ' ')
                            value = h.unescape(value)

                        if item == 'version':
                            try:
                                # Breakdown the version information for more detailed analysis
                                version_details = semantic_version.Version(value, partial=True)
                                if version_details.major is not None:
                                    template_block += "|Version major=%s\n" % version_details.major
                                if version_details.minor is not None:
                                    template_block += "|Version minor=%s\n" % version_details.minor
                                if version_details.patch is not None:
                                    template_block += "|Version patch=%s\n" % version_details.patch
                                if version_details.prerelease is not None:
                                    prerelease_string = ','.join(version_details.prerelease)
                                    template_block += "|Version prerelease=%s\n" % prerelease_string
                                if version_details.build is not None:
                                    build_string = ','.join(version_details.build)
                                    template_block += "|Version build=%s\n" % build_string
                            except Exception, e:
                                LOGGER.debug("Unable to parse version string %s (%s)" % (value, e))

                        if item == 'author':
                            # Authors can have a lot of junk in them, wikitext and such.
                            # We'll try to clean that up.

                            # Wikilinks with names
                            # "[[Foobar | Foo Bar]]"
                            value = re.sub(r'\[\[.*\|(.*)\]\]', r'\1', value)
                            # Simple Wikilinks
                            value = re.sub(r'\[\[(.*)\]\]', r'\1', value)
                            # Hyperlinks as wikiext
                            # "[https://www.mediawiki.org/wiki/User:Jeroen_De_Dauw Jeroen De Dauw]"
                            value = re.sub(r'\[\S+\s+([^\]]+)\]', r'\1', value)
                            # Misc text
                            value = re.sub(r'\sand\s', r', ', value)
                            value = re.sub(r'\.\.\.', r'', value)
                            value = re.sub(r'&nbsp;', r' ', value)
                            # Lastly, there could be HTML encoded stuff in these
                            value = h.unescape(value)

                        if item == 'url':
                            # Seems some people really really love protocol agnostic URL's
                            # We detect them and add a generic http: protocol to them
                            if re.match(r'^\/\/', value):
                                value = 'http:' + value

                        template_block += "|%s=%s\n" % (name, value)

                template_block += "}}\n"

        template_block += "</includeonly>"

        return template_block

