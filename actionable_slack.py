# (c) 2012-2014, Michael DeHaan <michael.dehaan@gmail.com>
# (C) 2014-2015, Matt Martz <matt@sivel.net>
# (c) 2015, Andrew Gaffney <andrew@agaffney.org>
# (C) 2017 Ansible Project
# (C) 2018, Rob Cascella <rob@qualpay.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = '''
    callback: actionable_slack
    callback_type: notification
    version_added: '2.5'
    requirements:
      - whitelist in configuration
      - prettytable (python library)
    short_description: Sends play and task events to a Slack channel
    description:
        - This ansible callback plugin sends status updates to a Slack channel during playbook execution.
        - It is based off the slack callback plugin, and borrows also from default and actionable.
        - This callback plugin sends actionable notifications to the Slack channel.
    options:
      webhook_url:
        required: True
        description: Slack Webhook URL
        env:
          - name: ACTIONABLE_SLACK_WEBHOOK_URL
        ini:
          - section: callback_actionable_slack
            key: webhook_url
      channel:
        default: "#ansible"
        description: Slack room to post in.
        env:
          - name: ACTIONABLE_SLACK_CHANNEL
        ini:
          - section: callback_actionable_slack
            key: channel
      terse_channel:
        default: "#fluffy-clouds"
        description: Slack room to post abbreviated messages in.
        env:
          - name: ACTIONABLE_SLACK_TERSE_CHANNEL
        ini:
          - section: callback_actionable_slack
            key: terse_channel
      username:
        description: Username to post as.
        env:
          - name: ACTIONABLE_SLACK_USERNAME
        default: ansible
        ini:
          - section: callback_actionable_slack
            key: username
'''

import json
import os
import uuid

try:
    from __main__ import cli
except ImportError:
    cli = None

from ansible.module_utils.urls import open_url
from ansible.plugins.callback import CallbackBase

try:
    import prettytable
    HAS_PRETTYTABLE = True
except ImportError:
    HAS_PRETTYTABLE = False


class CallbackModule(CallbackBase):
    """This is an ansible callback plugin that sends status
    updates to a Slack channel during playbook execution.
    """
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'actionable_slack'
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self, display=None):

        super(CallbackModule, self).__init__(display=display)

        if cli:
            self._options = cli.options
            #print('%s' % self._options)
            #print('%s' % dir(self._options))
        else:
            self._options = None
        #print('%s' % dir(self))
        #print('%s' % dir(self._options))
        #print('%s' % self._options)
        
        if not HAS_PRETTYTABLE:
            self.disabled = True
            self._display.warning('The `prettytable` python module is not '
                                  'installed. Disabling the Slack callback '
                                  'plugin.')

        self.playbook_name = None
        self.last_task = None
        self.notified_elsewhere = False

        if self._options.subset:
            self.limit = self._options.subset
        else:
            self.limit = None

        if self._options.check:
            self.task_status = 'dryrun'
            self.task_status_color = 'good'
            self.itwasa = 'testing'
        else:
            self.task_status = 'changed'
            self.task_status_color = 'warning'
            self.itwasa = 'playbook'

        # This is a 6 character identifier provided with each message
        # This makes it easier to correlate messages when there are more
        # than 1 simultaneous playbooks running
        self.guid = uuid.uuid4().hex[:6]

    def deliver_msg(self, msg, channel, color):
        attachments = [{
            'fallback': msg,
            'fields': [
                {
                    'value': msg
                }
            ],
            'color': color,
            'mrkdwn_in': ['text', 'fallback', 'fields'],
        }]
        payload = {
            'channel': channel,
            'username': self.username,
            'attachments': attachments,
            'parse': 'none',
            'icon_url': ('http://cdn2.hubspot.net/hub/330046/'
                         'file-449187601-png/ansible_badge.png'),
        }
        data = json.dumps(payload)
        self._display.debug(data)
        self._display.debug(self.webhook_url)
        try:
            response = open_url(self.webhook_url, data=data)
            return response.read()
        except Exception as e:
            self._display.warning('Could not submit message to Slack: %s' %
                                  str(e))

    def notify_elsewhere(self):
        if not self.notified_elsewhere:
            self.notified_elsewhere = True
            msg = '[%s] ansible run has taken action, %s: %s (see #ansible for more details!)' % (self.guid, self.itwasa, self.playbook_name)
            if self.limit:
                msg += ', limit: %s' % self.limit
            self.deliver_msg(msg, channel=self.terse_channel, color=self.task_status_color)

    def set_options(self, task_keys=None, var_options=None, direct=None):

        super(CallbackModule, self).set_options(task_keys=task_keys, var_options=var_options, direct=direct)

        self.webhook_url = self.get_option('webhook_url')
        self.channel = self.get_option('channel')
        self.terse_channel = self.get_option('terse_channel')
        self.username = self.get_option('username')

        if self.webhook_url is None:
            self.disabled = True
            self._display.warning('Slack Webhook URL was not provided. The '
                                  'Slack Webhook URL can be provided using '
                                  'the `ACTIONABLE_SLACK_WEBHOOK_URL` '
                                  'environment variable.')

#    def v2_on_any(self, *args, **kwargs):
#        #self._display.display('')
#        #self._display.display('')
#        self._display.display("--- play: {0} task: {1} ---".format(getattr(self.play, 'name', None), self.task))
#
#        self._display.display("     --- ARGS ")
#        for i, a in enumerate(args):
#            self._display.display('     %s: %s' % (i, a))
#
#        self._display.display("      --- KWARGS ")
#        for k in kwargs:
#            self._display.display('     %s: %s' % (k, kwargs[k]))

    def v2_playbook_on_task_start(self, task, is_conditional):
        self.last_task = task

    def v2_playbook_on_handler_task_start(self, task):
        self.last_task = task

    def v2_playbook_on_cleanup_task_start(self, task):
        self.last_task = task

    def v2_runner_on_failed(self, result, ignore_errors=False):
        if ignore_errors:
            return
        msg = "*fatal* (_%s_): [%s]: FAILED! => %s -=- %s" % (self.guid, result._host.get_name(), self.last_task, result._result.get('msg'))
        if not self._options.check:
            self.notify_elsewhere()
        self.deliver_msg(msg, channel=self.channel, color='danger')

    def v2_runner_on_ok(self, result):
        #print('checkmode: %s' % result._task_fields['args'].get('_ansible_check_mode'))
        if result._result.get('changed', False):
            msg = '*%s* (_%s_): [%s]: %s! => %s' % (self.task_status, self.guid, result._host.get_name(), self.task_status.upper(), self.last_task)
            if not self._options.check:
                self.notify_elsewhere()
            self.deliver_msg(msg, channel=self.channel, color=self.task_status_color)

    def v2_runner_on_unreachable(self, result):
        msg = '*host unreachable (_%s_):* [%s] => %s' % (self.guid, result._host.get_name(), result._result.get('msg'))
        self.deliver_msg(msg, channel=self.channel, color='danger')

    def v2_playbook_on_start(self, playbook):
        self.playbook_name = os.path.basename(playbook._file_name)
        msg = '*%s initiated* (_%s_): %s' % (self.itwasa, self.guid, self.playbook_name)
        if self.limit:
            msg += ', limit: %s' % self.limit
        self.deliver_msg(msg, channel=self.channel, color=self.task_status_color)

    def v2_playbook_on_stats(self, stats):
        """Display info about playbook statistics"""

        hosts = sorted(stats.processed.keys())

        t = prettytable.PrettyTable(['Host', 'Ok', 'Changed', 'Unreachable',
                                     'Failures'])

        failures = False
        unreachable = False

        for h in hosts:
            s = stats.summarize(h)

            if s['failures'] > 0:
                failures = True
            if s['unreachable'] > 0:
                unreachable = True

            t.add_row([h] + [s[k] for k in ['ok', 'changed', 'unreachable',
                                            'failures']])

        attachments = []

        msg_items = [
            '*%s complete* (_%s_)' % (self.itwasa, self.guid)
        ]

        if failures or unreachable:
            color = 'danger'
        else:
            color = 'good'

        msg_items.append('```\n%s\n```' % t)

        msg = '\n'.join(msg_items)

        self.deliver_msg(msg, channel=self.channel, color=color)
        if not self._options.check and self.notified_elsewhere:
            msg = '[%s] ansible %s complete: %s (see #ansible for more details!)' % (self.guid, self.itwasa, self.playbook_name)
            self.deliver_msg(msg, channel=self.terse_channel, color=color)
