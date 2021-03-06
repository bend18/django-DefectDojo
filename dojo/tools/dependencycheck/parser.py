import hashlib
import logging
import re

from defusedxml import ElementTree

from dojo.models import Finding

logger = logging.getLogger(__name__)


class DependencyCheckParser(object):
    def get_field_value(self, parent_node, field_name):
        field_node = parent_node.find(self.namespace + field_name)
        field_value = u'' if field_node is None else field_node.text
        return field_value

    def get_filename_from_dependency(self, dependency):
        return self.get_field_value(dependency, 'fileName')

    def get_finding_from_vulnerability(self, vulnerability, filename, test):
        name = self.get_field_value(vulnerability, 'name')
        severity = self.get_field_value(vulnerability, 'severity')
        cwe_field = self.get_field_value(vulnerability, 'cwe')
        description = self.get_field_value(vulnerability, 'description')

        title = u'{0} | {1}'.format(filename, name)

        # Use CWE-1035 as fallback
        cwe = 1035  # Vulnerable Third Party Component
        if cwe_field:
            m = re.match(r"^(CWE-)?(\d+)", cwe_field)
            if m:
                cwe = int(m.group(2))

        reference_detail = None
        references_node = vulnerability.find(self.namespace + 'references')

        if references_node is not None:
            reference_detail = ''
            for reference_node in references_node.findall(self.namespace +
                                                          'reference'):
                name = self.get_field_value(reference_node, 'name')
                source = self.get_field_value(reference_node, 'source')
                url = self.get_field_value(reference_node, 'url')
                reference_detail += u'name: {0}\n' \
                                     'source: {1}\n' \
                                     'url: {2}\n\n'.format(name, source, url)

        return Finding(
            title=title,
            file_path=filename,
            test=test,
            cwe=cwe,
            active=False,
            verified=False,
            description=description,
            severity=severity,
            numerical_severity=Finding.get_numerical_severity(severity),
            static_finding=True,
            references=reference_detail)

    def __init__(self, filename, test):
        self.dupes = dict()
        self.items = ()
        self.namespace = ''

        if filename is None:
            return

        content = filename.read()

        if content is None:
            return

        scan = ElementTree.fromstring(content)
        regex = r"{.*}"
        matches = re.match(regex, scan.tag)
        self.namespace = matches.group(0)

        dependencies = scan.find(self.namespace + 'dependencies')

        if dependencies:
            for dependency in dependencies.findall(self.namespace +
                                                   'dependency'):
                dependency_filename = self.get_filename_from_dependency(
                    dependency)
                vulnerabilities = dependency.find(self.namespace +
                                                  'vulnerabilities')
                if vulnerabilities is not None:
                    for vulnerability in vulnerabilities.findall(
                            self.namespace + 'vulnerability'):
                        finding = self.get_finding_from_vulnerability(
                            vulnerability, dependency_filename, test)

                        if finding is not None:
                            key_str = u'{}|{}|{}'.format(finding.severity,
                                                         finding.title,
                                                         finding.description)
                            key = hashlib.md5(key_str.encode('utf-8')).hexdigest()

                            if key not in self.dupes:
                                self.dupes[key] = finding

        self.items = self.dupes.values()
