import asyncio

from telnetlib3 import TelnetServer, create_server, telopt

import bbs.models
from bbs.command_processor import MainProcessor
from bbs.readline import Readline


class LONRTelnetServer(TelnetServer):
    def on_timeout(self):
        """
        Callback received on session timeout.
        Overrides on_timeout in TelnetServer class.
        
        This can be disabled by calling :meth:`set_timeout` with
        :paramref:`~.set_timeout.duration` value of ``0`` or value of
        the same for keyword argument ``timeout``.
        """
        self.log.debug('Timeout after {self.idle:1.2f}s'.format(self=self))
        self.writer.write('\r\n* poof *\r\n')
        self.writer.close()


async def login(reader, writer):
    writer.write("\r\n\r\nWelcome to the Land of No Return!\r\n")
    writer.write('\r\nState thy name, or enter "new" to register.\r\n')
    username = await reader.prompt('username: ')
    if username == 'new':
        new_username = await reader.prompt('\r\n\r\nHow will thy name be known around these parts? [Q=Quit]: ')
        if new_username.lower() == 'q':
            return None

        check_user = await bbs.models.User.get_user(new_username)
        if check_user is not None:
            writer.write('\r\n*** That name is already in use!\r')
            return None

        with reader.no_echo():
            new_password = await reader.prompt('\r\n\r\nEnter a password to use with the guards: ')
            new_password_check = await reader.prompt('\r\nEnter again to verify: ')
        if new_password != new_password_check:
            writer.write('\r\n*** Passwords do not match!\r\n')
            return None
        user = await bbs.models.User.new_user(
            username=new_username,
            password=new_password,
            email=f'{new_username}@lonr.hivenoise.com',
            can_chat=True,
            is_admin=False,
        )
        username = new_username
        writer.write('\r\nYou have been registered.  Please continue your visit...\r\n')

    user = await bbs.models.User.get_user(username)
    if user is None:
        writer.write("\r\nUnknown username.")
        return None
    with reader.no_echo():
        password = await reader.prompt('\r\npassword: ')
    if user.verify(password):
        return user
    writer.write("\r\nInvalid password.")
    return None


async def negotiate_telnet_options(writer):
    """
    Negotiate the telnet connection options with the client.
    """
    writer.iac(telopt.DO, telopt.NAWS)
    writer.iac(telopt.DO, telopt.SGA)
    writer.iac(telopt.WILL, telopt.SGA)
    writer.iac(telopt.WILL, telopt.ECHO)
    writer.iac(telopt.WONT, telopt.LINEMODE)
    rows = writer.get_extra_info('rows', 24)
    cols = writer.get_extra_info('cols', 80)

    # Give the client a bit of time to respond to the commands before starting.
    await asyncio.sleep(0.5)
    return rows, cols


async def shell(reader, writer):
    rows, cols = await negotiate_telnet_options(writer)
    reader, writer = Readline.wrap_streams(reader, writer)

    user = None
    while not user:
        user = await login(reader, writer)
        if user == reader.BREAK:
            await writer.drain()
            writer.close()
            return
        writer.write('\r\n')
    writer.write(f'Greetings, {user}!\r\n')
    # writer.write(f'Your home directory is {await (await user.home).full_path()}\r\n')
    writer.write((await MainProcessor(user, reader, writer).process()) + '\r\n')
    await writer.drain()
    writer.close()


async def start_telnet(host='', port=6023, timeout=300):
    return await create_server(
        host=host,
        port=port,
        shell=shell,
        timeout=timeout,
        protocol_factory=LONRTelnetServer,
    )
