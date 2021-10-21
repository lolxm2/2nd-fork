# This file is part of Buildbot.  Buildbot is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Buildbot Team Members

import stat

from twisted.internet import defer
from twisted.trial import unittest

from buildbot.interfaces import WorkerSetupError
from buildbot.process import buildstep
from buildbot.process import properties
from buildbot.process import remotetransfer
from buildbot.process.results import EXCEPTION
from buildbot.process.results import FAILURE
from buildbot.process.results import SUCCESS
from buildbot.steps import worker
from buildbot.test.fake.remotecommand import Expect
from buildbot.test.fake.remotecommand import ExpectCpdir
from buildbot.test.fake.remotecommand import ExpectDownloadFile
from buildbot.test.fake.remotecommand import ExpectGlob
from buildbot.test.fake.remotecommand import ExpectMkdir
from buildbot.test.fake.remotecommand import ExpectRemoteRef
from buildbot.test.fake.remotecommand import ExpectRmdir
from buildbot.test.fake.remotecommand import ExpectRmfile
from buildbot.test.fake.remotecommand import ExpectStat
from buildbot.test.fake.remotecommand import ExpectUploadFile
from buildbot.test.util import steps
from buildbot.test.util.misc import TestReactorMixin


def uploadString(string):
    def behavior(command):
        writer = command.args['writer']
        writer.remote_write(string)
        writer.remote_close()
    return behavior


class TestSetPropertiesFromEnv(steps.BuildStepMixin, TestReactorMixin,
                               unittest.TestCase):

    def setUp(self):
        self.setUpTestReactor()
        return self.setUpBuildStep()

    def tearDown(self):
        return self.tearDownBuildStep()

    def test_simple(self):
        self.setup_step(worker.SetPropertiesFromEnv(
            variables=["one", "two", "three", "five", "six"],
            source="me"))
        self.worker.worker_environ = {
            "one": "1", "two": None, "six": "6", "FIVE": "555"}
        self.worker.worker_system = 'linux'
        self.properties.setProperty("four", 4, "them")
        self.properties.setProperty("five", 5, "them")
        self.properties.setProperty("six", 99, "them")
        self.expectOutcome(result=SUCCESS,
                           state_string="Set")
        self.expectProperty('one', "1", source='me')
        self.expectNoProperty('two')
        self.expectNoProperty('three')
        self.expectProperty('four', 4, source='them')
        self.expectProperty('five', 5, source='them')
        self.expectProperty('six', '6', source='me')
        self.expectLogfile("properties",
                           "one = '1'\nsix = '6'")
        return self.run_step()

    def test_case_folding(self):
        self.setup_step(worker.SetPropertiesFromEnv(
            variables=["eNv"], source="me"))
        self.worker.worker_environ = {"ENV": 'EE'}
        self.worker.worker_system = 'win32'
        self.expectOutcome(result=SUCCESS,
                           state_string="Set")
        self.expectProperty('eNv', 'EE', source='me')
        self.expectLogfile("properties",
                           "eNv = 'EE'")
        return self.run_step()


class TestFileExists(steps.BuildStepMixin, TestReactorMixin,
                     unittest.TestCase):

    def setUp(self):
        self.setUpTestReactor()
        return self.setUpBuildStep()

    def tearDown(self):
        return self.tearDownBuildStep()

    def test_found(self):
        self.setup_step(worker.FileExists(file="x"))
        self.expectCommands(
            ExpectStat(file='x')
            .update('stat', [stat.S_IFREG, 99, 99])
            .exit(0)
        )
        self.expectOutcome(result=SUCCESS, state_string="File found.")
        return self.run_step()

    def test_not_found(self):
        self.setup_step(worker.FileExists(file="x"))
        self.expectCommands(
            ExpectStat(file='x')
            .update('stat', [0, 99, 99])
            .exit(0)
        )
        self.expectOutcome(result=FAILURE,
                           state_string="Not a file. (failure)")
        return self.run_step()

    def test_failure(self):
        self.setup_step(worker.FileExists(file="x"))
        self.expectCommands(
            ExpectStat(file='x')
            .exit(1)
        )
        self.expectOutcome(result=FAILURE,
                           state_string="File not found. (failure)")
        return self.run_step()

    def test_render(self):
        self.setup_step(worker.FileExists(file=properties.Property("x")))
        self.properties.setProperty('x', 'XXX', 'here')
        self.expectCommands(
            ExpectStat(file='XXX')
            .exit(1)
        )
        self.expectOutcome(result=FAILURE,
                           state_string="File not found. (failure)")
        return self.run_step()

    @defer.inlineCallbacks
    def test_old_version(self):
        self.setup_step(worker.FileExists(file="x"),
                       worker_version=dict())
        self.expectOutcome(result=EXCEPTION,
                           state_string="finished (exception)")
        yield self.run_step()
        self.flushLoggedErrors(WorkerSetupError)


class TestCopyDirectory(steps.BuildStepMixin, TestReactorMixin,
                        unittest.TestCase):

    def setUp(self):
        self.setUpTestReactor()
        return self.setUpBuildStep()

    def tearDown(self):
        return self.tearDownBuildStep()

    def test_success(self):
        self.setup_step(worker.CopyDirectory(src="s", dest="d"))
        self.expectCommands(
            ExpectCpdir(fromdir='s', todir='d', timeout=120)
            .exit(0)
        )
        self.expectOutcome(result=SUCCESS, state_string="Copied s to d")
        return self.run_step()

    def test_timeout(self):
        self.setup_step(worker.CopyDirectory(src="s", dest="d", timeout=300))
        self.expectCommands(
            ExpectCpdir(fromdir='s', todir='d', timeout=300)
            .exit(0)
        )
        self.expectOutcome(result=SUCCESS, state_string="Copied s to d")
        return self.run_step()

    def test_maxTime(self):
        self.setup_step(worker.CopyDirectory(src="s", dest="d", maxTime=10))
        self.expectCommands(
            ExpectCpdir(fromdir='s', todir='d', maxTime=10, timeout=120)
            .exit(0)
        )
        self.expectOutcome(result=SUCCESS, state_string="Copied s to d")
        return self.run_step()

    def test_failure(self):
        self.setup_step(worker.CopyDirectory(src="s", dest="d"))
        self.expectCommands(
            ExpectCpdir(fromdir='s', todir='d', timeout=120)
            .exit(1)
        )
        self.expectOutcome(result=FAILURE,
                           state_string="Copying s to d failed. (failure)")
        return self.run_step()

    def test_render(self):
        self.setup_step(worker.CopyDirectory(
            src=properties.Property("x"), dest=properties.Property("y")))
        self.properties.setProperty('x', 'XXX', 'here')
        self.properties.setProperty('y', 'YYY', 'here')
        self.expectCommands(
            ExpectCpdir(fromdir='XXX', todir='YYY', timeout=120)
            .exit(0)
        )
        self.expectOutcome(result=SUCCESS, state_string="Copied XXX to YYY")
        return self.run_step()


class TestRemoveDirectory(steps.BuildStepMixin, TestReactorMixin,
                          unittest.TestCase):

    def setUp(self):
        self.setUpTestReactor()
        return self.setUpBuildStep()

    def tearDown(self):
        return self.tearDownBuildStep()

    def test_success(self):
        self.setup_step(worker.RemoveDirectory(dir="d"))
        self.expectCommands(
            ExpectRmdir(dir='d')
            .exit(0)
        )
        self.expectOutcome(result=SUCCESS,
                           state_string="Deleted")
        return self.run_step()

    def test_failure(self):
        self.setup_step(worker.RemoveDirectory(dir="d"))
        self.expectCommands(
            ExpectRmdir(dir='d')
            .exit(1)
        )
        self.expectOutcome(result=FAILURE,
                           state_string="Delete failed. (failure)")
        return self.run_step()

    def test_render(self):
        self.setup_step(worker.RemoveDirectory(dir=properties.Property("x")))
        self.properties.setProperty('x', 'XXX', 'here')
        self.expectCommands(
            ExpectRmdir(dir='XXX')
            .exit(0)
        )
        self.expectOutcome(result=SUCCESS,
                           state_string="Deleted")
        return self.run_step()


class TestMakeDirectory(steps.BuildStepMixin, TestReactorMixin,
                        unittest.TestCase):

    def setUp(self):
        self.setUpTestReactor()
        return self.setUpBuildStep()

    def tearDown(self):
        return self.tearDownBuildStep()

    def test_success(self):
        self.setup_step(worker.MakeDirectory(dir="d"))
        self.expectCommands(
            ExpectMkdir(dir='d')
            .exit(0)
        )
        self.expectOutcome(result=SUCCESS, state_string="Created")
        return self.run_step()

    def test_failure(self):
        self.setup_step(worker.MakeDirectory(dir="d"))
        self.expectCommands(
            ExpectMkdir(dir='d')
            .exit(1)
        )
        self.expectOutcome(result=FAILURE, state_string="Create failed. (failure)")
        return self.run_step()

    def test_render(self):
        self.setup_step(worker.MakeDirectory(dir=properties.Property("x")))
        self.properties.setProperty('x', 'XXX', 'here')
        self.expectCommands(
            ExpectMkdir(dir='XXX')
            .exit(0)
        )
        self.expectOutcome(result=SUCCESS, state_string="Created")
        return self.run_step()


class CompositeUser(buildstep.BuildStep, worker.CompositeStepMixin):

    def __init__(self, payload):
        self.payload = payload
        self.logEnviron = False
        super().__init__()

    @defer.inlineCallbacks
    def run(self):
        yield self.addLogForRemoteCommands('stdio')
        res = yield self.payload(self)
        return FAILURE if res else SUCCESS


class TestCompositeStepMixin(steps.BuildStepMixin, TestReactorMixin,
                             unittest.TestCase):

    def setUp(self):
        self.setUpTestReactor()
        return self.setUpBuildStep()

    def tearDown(self):
        return self.tearDownBuildStep()

    def test_runRemoteCommand(self):
        cmd_args = ('foo', {'bar': False})

        def testFunc(x):
            x.runRemoteCommand(*cmd_args)
        self.setup_step(CompositeUser(testFunc))
        self.expectCommands(Expect(*cmd_args)
                            .exit(0))
        self.expectOutcome(result=SUCCESS)

    def test_runRemoteCommandFail(self):
        cmd_args = ('foo', {'bar': False})

        @defer.inlineCallbacks
        def testFunc(x):
            yield x.runRemoteCommand(*cmd_args)
        self.setup_step(CompositeUser(testFunc))
        self.expectCommands(Expect(*cmd_args)
                            .exit(1))
        self.expectOutcome(result=FAILURE)
        return self.run_step()

    @defer.inlineCallbacks
    def test_runRemoteCommandFailNoAbandon(self):
        cmd_args = ('foo', {'bar': False})

        @defer.inlineCallbacks
        def testFunc(x):
            yield x.runRemoteCommand(*cmd_args,
                                     **dict(abandonOnFailure=False))
            testFunc.ran = True
        self.setup_step(CompositeUser(testFunc))
        self.expectCommands(Expect(*cmd_args)
                            .exit(1))
        self.expectOutcome(result=SUCCESS)
        yield self.run_step()
        self.assertTrue(testFunc.ran)

    def test_rmfile(self):
        self.setup_step(CompositeUser(lambda x: x.runRmFile("d")))
        self.expectCommands(
            ExpectRmfile(path='d', logEnviron=False)
            .exit(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.run_step()

    def test_mkdir(self):
        self.setup_step(CompositeUser(lambda x: x.runMkdir("d")))
        self.expectCommands(
            ExpectMkdir(dir='d', logEnviron=False)
            .exit(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.run_step()

    def test_rmdir(self):
        self.setup_step(CompositeUser(lambda x: x.runRmdir("d")))
        self.expectCommands(
            ExpectRmdir(dir='d', logEnviron=False)
            .exit(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.run_step()

    def test_mkdir_fail(self):
        self.setup_step(CompositeUser(lambda x: x.runMkdir("d")))
        self.expectCommands(
            ExpectMkdir(dir='d', logEnviron=False)
            .exit(1)
        )
        self.expectOutcome(result=FAILURE)
        return self.run_step()

    def test_glob(self):
        @defer.inlineCallbacks
        def testFunc(x):
            res = yield x.runGlob("*.pyc")
            self.assertEqual(res, ["one.pyc", "two.pyc"])

        self.setup_step(CompositeUser(testFunc))
        self.expectCommands(
            ExpectGlob(path='*.pyc', logEnviron=False)
            .update('files', ["one.pyc", "two.pyc"])
            .exit(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.run_step()

    def test_glob_fail(self):
        self.setup_step(CompositeUser(lambda x: x.runGlob("*.pyc")))
        self.expectCommands(
            ExpectGlob(path='*.pyc', logEnviron=False)
            .exit(1)
        )
        self.expectOutcome(result=FAILURE)
        return self.run_step()

    def test_abandonOnFailure(self):
        @defer.inlineCallbacks
        def testFunc(x):
            yield x.runMkdir("d")
            yield x.runMkdir("d")
        self.setup_step(CompositeUser(testFunc))
        self.expectCommands(
            ExpectMkdir(dir='d', logEnviron=False)
            .exit(1)
        )
        self.expectOutcome(result=FAILURE)
        return self.run_step()

    def test_notAbandonOnFailure(self):
        @defer.inlineCallbacks
        def testFunc(x):
            yield x.runMkdir("d", abandonOnFailure=False)
            yield x.runMkdir("d", abandonOnFailure=False)
        self.setup_step(CompositeUser(testFunc))
        self.expectCommands(
            ExpectMkdir(dir='d', logEnviron=False)
            .exit(1),
            ExpectMkdir(dir='d', logEnviron=False)
            .exit(1)
        )
        self.expectOutcome(result=SUCCESS)
        return self.run_step()

    def test_getFileContentFromWorker(self):
        @defer.inlineCallbacks
        def testFunc(x):
            res = yield x.getFileContentFromWorker("file.txt")
            self.assertEqual(res, "Hello world!")

        self.setup_step(CompositeUser(testFunc))
        self.expectCommands(
            ExpectUploadFile(workersrc="file.txt", workdir='wkdir',
                             blocksize=32 * 1024, maxsize=None,
                             writer=ExpectRemoteRef(remotetransfer.StringFileWriter))
            .upload_string("Hello world!")
            .exit(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.run_step()

    def test_getFileContentFromWorker2_16(self):
        @defer.inlineCallbacks
        def testFunc(x):
            res = yield x.getFileContentFromWorker("file.txt")
            self.assertEqual(res, "Hello world!")

        self.setup_step(
            CompositeUser(testFunc),
            worker_version={'*': '2.16'})
        self.expectCommands(
            ExpectUploadFile(slavesrc="file.txt", workdir='wkdir',
                             blocksize=32 * 1024, maxsize=None,
                             writer=ExpectRemoteRef(remotetransfer.StringFileWriter))
            .upload_string("Hello world!")
            .exit(0)
        )
        self.expectOutcome(result=SUCCESS)
        return self.run_step()

    def test_downloadFileContentToWorker(self):
        @defer.inlineCallbacks
        def testFunc(x):
            res = yield x.downloadFileContentToWorker("/path/dest1", "file text")
            self.assertEqual(res, None)

        self.setup_step(CompositeUser(testFunc))
        self.expectCommands(
            ExpectDownloadFile(maxsize=None, workdir='wkdir', mode=None,
                               reader=ExpectRemoteRef(remotetransfer.FileReader),
                               blocksize=32768, workerdest='/path/dest1')
        )
        self.expectOutcome(result=SUCCESS)
        return self.run_step()

    def test_downloadFileContentToWorkerWithFilePermissions(self):
        @defer.inlineCallbacks
        def testFunc(x):
            res = yield x.downloadFileContentToWorker("/path/dest1", "file text", mode=stat.S_IRUSR)
            self.assertEqual(res, None)

        self.setup_step(CompositeUser(testFunc))
        self.expectCommands(
            ExpectDownloadFile(maxsize=None, workdir='wkdir', mode=stat.S_IRUSR,
                               reader=ExpectRemoteRef(remotetransfer.FileReader),
                               blocksize=32768, workerdest='/path/dest1')
        )
        self.expectOutcome(result=SUCCESS)
        return self.run_step()
