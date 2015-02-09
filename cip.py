__author__ = "Agostino Ruscito <ruscito@gmail.com>"
__status__ = "testing"
__version__ = "0.1"
__date__ = "01 01 2015"

from cip_base import *
import logging

logger = logging.getLogger(__name__)


class TagList:
    def __init__(self):
        self.tagList = []

    def add_tag(self, t):
        self.tagList.append(t)


class Cip:
    def __init__(self):
        self.__version__ = '0.1'
        self.__sock = Socket(None)
        self.session = 0
        self.context = '_pycomm_'
        self.protocol_version = 1
        self.general_status = 0
        self.extend_status = 0
        self.option = 0
        self.port = 0xAF12
        self.connection_opened = False
        self._replay = None
        self._message = None
        self.cid = '\x27\x04\x19\x71'
        self.csn = '\x27\x04'
        self.vid = '\x09\x10'
        self.vsn = '\x09\x10\x19\x71'
        self.target_cid = None
        self.target_is_connected = False
        self._sequence = 1
        self.backplane = 1
        self.cpu_slot = 0
        self.rpi = 5000
        setup_logging()

    def get_extended_status(self):
        """
        Return the extend status.

        Status is  3 byte  after Replay Service Replay Service 1 byte long.
        """
        if ord(self._replay[43]) == 0:
            # no extend_status
            return 0
        else:
            # Extended status should be 2 byte
            self.extend_status = unpack_uint(self._replay[44:45])
        return self.extend_status

    def build_header(self, command, length):
        """
        build the encapsulated message header which is a 24 bytes fixed length.
        The header includes the command and the length of the optional data portion
        """
        h = command                     # Command UINT
        h += pack_uint(length)          # Length UINT
        h += pack_dint(self.session)    # Session Handle UDINT
        h += pack_dint(0)               # Status UDINT
        h += self.context               # Sender Context 8 bytes
        h += pack_dint(self.option)     # Option UDINT
        return h

    def nop(self):
        logger.debug('>>> nop')
        self._message = self.build_header(ENCAPSULATION_COMMAND['nop'], 0)
        self.send()
        logger.debug('nop >>>')

    def list_identity(self):
        logger.debug('>>> list_identity')
        self._message = self.build_header(ENCAPSULATION_COMMAND['list_identity'], 0)
        self.send()
        self.receive()
        logger.debug('list_identity >>>')

    def register_session(self):
        logger.debug('>>> register_session')
        if self.session:
            logger.warn('Session already registered')
            return self.session

        self._message = self.build_header(ENCAPSULATION_COMMAND['register_session'], 4)
        self._message += pack_uint(self.protocol_version)
        self._message += pack_uint(0)
        self.send()
        self.receive()
        if self._check_replay():
            self.session = unpack_dint(self._replay[4:8])
            logger.debug('register_session (session =%s) >>>' % print_bytes_line(self._replay[4:8]))
            return self.session
        logger.warn('Leaving register_session (session =None) >>>')
        return None

    def un_register_session(self):
        logger.debug('>>> un_register_session')
        self._message = self.build_header(ENCAPSULATION_COMMAND['unregister_session'], 0)
        self.send()
        self.session = None
        logger.debug('un_register_session >>>')

    def send_rr_data(self, msg):
        logger.debug('>>> send_rr_data')
        self._message = self.build_header(ENCAPSULATION_COMMAND["send_rr_data"], len(msg))
        self._message += msg
        self.send()
        self.receive()
        logger.debug('send_rr_data >>>')
        return self._check_replay()

    def send_unit_data(self, msg):
        logger.debug('>>> send_unit_data')
        self._message = self.build_header(ENCAPSULATION_COMMAND["send_unit_data"], len(msg))
        self._message += msg
        self.send()
        self.receive()
        logger.debug('send_unit_data >>>')
        return self._check_replay()

    def _get_sequence(self):
        if self._sequence < 65535:
            self._sequence += 1
        else:
            self._sequence = 1
        return self._sequence

    def _check_replay(self):
        """ _check_replay

        """
        if self._replay is None:
            logger.warning('%s without reply' % REPLAY_INFO[unpack_dint(self._message[:2])])
            return False
        # Get the type of command
        typ = unpack_uint(self._replay[:2])

        # Encapsulation status check
        if unpack_dint(self._replay[8:12]) != SUCCESS:
            logger.warning('%s reply error' % REPLAY_INFO[typ])
            logger.warning('{0} reply status:{1}'.format(
                REPLAY_INFO[typ],
                SERVICE_STATUS[unpack_dint(self._replay[8:12])]
            ))
            return False

        # Command Specific Status check
        if typ == unpack_uint(ENCAPSULATION_COMMAND["send_rr_data"]):
            status = unpack_sint(self._replay[42:43])
            # Exit if  send_rr_data replay returned error
            # 42 General Status
            # 43 Size of additional status
            # 44..n additional status
            if status != SUCCESS:
                logger.warning('{0} reply status {1}: {2}'.format(
                    REPLAY_INFO[unpack_sint(self._message[40:41])],
                    "{:0>2x} ".format(ord(self._replay[42:43])),
                    SERVICE_STATUS[status]
                ))
                extended_status_size = unpack_sint(self._replay[43:44])
                if extended_status_size != 0:
                    # There is an additional status
                    try:
                        if extended_status_size == 1:
                            extended_status = unpack_sint(self._replay[44:45])
                        elif extended_status_size == 2:
                            extended_status = unpack_sint(self._replay[44:46])
                        elif extended_status_size == 4:
                            extended_status = unpack_dint(self._replay[44:48])
                        else:
                            logger.warning('Extended Status Size Unknown')
                            return False
                    except LookupError:
                        logger.warning('Extended status [{0}] not coded '.format(pack_dint(extended_status)))
                        return False
                    logger.warning('Extended status :{0}'.format(EXTEND_CODES[status][extended_status]))
                    return False
        elif typ == unpack_uint(ENCAPSULATION_COMMAND["send_unit_data"]):
            # Exit if  send_unit_data replay returned error
            # 48 General Status
            # 49 Size of additional status
            # 50..n additional status
            status = unpack_sint(self._replay[48:49])
            if status != SUCCESS:
                logger.debug(print_bytes_msg(self._replay))
                logger.warning('{0} reply status {1}: {2}'.format(
                    TAG_SERVICES_REPLAY[unpack_sint(self._replay[46:47])],
                    "{:0>2x} ".format(ord(self._replay[48:49])),
                    SERVICE_STATUS[status]
                ))
                extended_status_size = unpack_sint(self._replay[49:50])
                if extended_status_size != 0:
                    # There is an additional status
                    try:
                        if extended_status_size == 1:
                            extended_status = unpack_sint(self._replay[50:51])
                        elif extended_status_size == 2:
                            extended_status = unpack_sint(self._replay[50:52])
                        elif extended_status_size == 4:
                            extended_status = unpack_dint(self._replay[50:54])
                        else:
                            logger.warning('Extended Status Size Unknown')
                            return False
                    except LookupError:
                        logger.warning('Extended status [{0}] not coded '.format(pack_dint(extended_status)))
                        return False
                    logger.warning('Extended status :{0}'.format(EXTEND_CODES[status][extended_status]))
                    return False
        elif typ not in REPLAY_INFO:
            logger.warning('Replay to unknown encapsulation message [%d]' % typ)
            return False

        return True

    @staticmethod
    def create_tag_rp(tag):
        """ Create tag Request Packet

        """
        tags = tag.split('.')
        rp = []
        index = []
        for tag in tags:
            add_index = False
            # Check if is an array tag
            if tag.find('[') != -1:
                # Remove the last square bracket
                tag = tag[:len(tag)-1]
                # Isolate the value inside bracket
                inside_value = tag[tag.find('[')+1:]
                # Now split the inside value in case part of multidimensional array
                index = inside_value.split(',')
                # Flag the existence of one o more index
                add_index = True
                # Get only the tag part
                tag = tag[:tag.find('[')]
            tag_length = len(tag)
            # Create the request path
            rp.append(EXTENDED_SYMBOL)  # ANSI Ext. symbolic segment
            rp.append(chr(tag_length))  # Length of the tag
            # Add the tag to the Request path
            for char in tag:
                rp.append(char)
            # Add pad byte because total length of Request path must be word-aligned
            if tag_length % 2:
                rp.append('\x00')
            # Add any index
            if add_index:
                for idx in index:
                    val = int(idx)
                    if val <= 0xff:
                        rp.append('\x28')
                        rp.append(pack_sint(val))
                    elif val <= 0xffff:
                        rp.append('\x29\x00')
                        rp.append(pack_uint(val))
                    elif val <= 0xfffffffff:
                        rp.append('\x2a\x00')
                        rp.append(pack_dint(val))
                    else:
                        logger.warning('create_tag_rp tag index error {0}[{1}]'.format(tag, val))
                        return None

        # At this point the Request Path is completed,
        return ''.join(rp)

    @staticmethod
    def build_common_cpf(message_type, message, addr_type, addr_data=None, timeout=0):
        msg = pack_dint(0)   # Interface Handle: shall be 0 for CIP
        msg += pack_uint(timeout)   # timeout
        msg += pack_uint(2)  # Item count: should be at list 2 (Address and Data)
        msg += addr_type  # Address Item Type ID

        if addr_data is not None:
            msg += pack_uint(len(addr_data))  # Address Item Length
            msg += addr_data
        else:
            msg += pack_uint(0)  # Address Item Length
        msg += message_type  # Data Type ID
        msg += pack_uint(len(message))   # Data Item Length
        msg += message
        return msg

    def forward_open(self):
        logger.debug('>>> forward_open')
        if self.session == 0:
            logger.warning("Session not registered yet.")
            return None

        forward_open_msg = [
            FORWARD_OPEN,
            pack_sint(2),
            CLASS_ID["8-bit"],
            CLASS_CODE["Connection Manager"],  # Volume 1: 5-1
            INSTANCE_ID["8-bit"],
            CONNECTION_MANAGER_INSTANCE['Open Request'],
            PRIORITY,
            TIMEOUT_TICKS,
            pack_dint(0),
            self.cid,
            self.csn,
            self.vid,
            self.vsn,
            TIMEOUT_MULTIPLIER,
            '\x00\x00\x00',
            pack_dint(self.rpi*1000),
            pack_uint(CONNECTION_PARAMETER['Default']),
            pack_dint(self.rpi*1000),
            pack_uint(CONNECTION_PARAMETER['Default']),
            TRANSPORT_CLASS,  # Transport Class
            CONNECTION_SIZE['Backplane'],
            pack_sint(self.backplane),
            pack_sint(self.cpu_slot),
            CLASS_ID["8-bit"],
            CLASS_CODE["Message Router"],
            INSTANCE_ID["8-bit"],
            pack_sint(1)
        ]

        if self.send_rr_data(
                Cip.build_common_cpf(
                        DATA_ITEM['Unconnected'],
                        ''.join(forward_open_msg),
                        ADDRESS_ITEM['Null'],
                        timeout=1
                )):
            self.target_cid = self._replay[44:48]
            self.target_is_connected = True
            logger.info("The target is connected end returned CID %s" % print_bytes_line(self.target_cid))
            logger.debug('forward_open >>>')
            return True
        logger.warning('forward_open returning False>>>')
        return False

    def forward_close(self, backplane=1, cpu_slot=0):
        logger.debug('>>> forward_close')
        if self.session == 0:
            logger.warning("Session not registered yet.")
            return None

        forward_close_msg = [
            FORWARD_CLOSE,
            pack_sint(2),
            CLASS_ID["8-bit"],
            CLASS_CODE["Connection Manager"],  # Volume 1: 5-1
            INSTANCE_ID["8-bit"],
            CONNECTION_MANAGER_INSTANCE['Open Request'],
            PRIORITY,
            TIMEOUT_TICKS,
            self.csn,
            self.vid,
            self.vsn,
            CONNECTION_SIZE['Backplane'],
            '\x00',     # Reserved
            pack_sint(backplane),
            pack_sint(cpu_slot),
            CLASS_ID["8-bit"],
            CLASS_CODE["Message Router"],
            INSTANCE_ID["8-bit"],
            pack_sint(1)
        ]
        if self.send_rr_data(
                Cip.build_common_cpf(
                        DATA_ITEM['Unconnected'],
                        ''.join(forward_close_msg),
                        ADDRESS_ITEM['Null'],
                        timeout=1
                )):
            self.target_is_connected = False
            logger.debug('forward_close >>>')
            return True
        logger.warning('forward_close returning False>>>')
        return False


    def read_tag(self, tag):
        """ read_tag

        """
        logger.debug('>>> read_tag')
        if self.session == 0:
            logger.warning("Session not registered yet.")
            return None

        if not self.target_is_connected:
            logger.debug('target not connected yet. Will execute a forward_open to connect')
            if not self.forward_open():
                logger.warning("Target did not connected")
                return None

        rp = Cip.create_tag_rp(tag)

        if rp is None:
            logger.warning('Cannot create tag {0} request packet. Read not executed'.format(tag))
            return None

        # Creating the Message Request Packet
        message_request = [
            pack_uint(self._get_sequence()),
            chr(TAG_SERVICES_REQUEST['Read Tag']),  # the Request Service
            chr(len(rp) / 2),                       # the Request Path Size length in word
            rp,                                     # the request path
            pack_uint(1),                           # Add the number of tag to read
        ]

        if self.send_unit_data(
                Cip.build_common_cpf(
                    DATA_ITEM['Connected'],
                    ''.join(message_request),
                    ADDRESS_ITEM['Connection Based'],
                    addr_data=self.target_cid,
                    timeout=1
                )):
            # Get the data type
            for key, value in DATA_TYPE.iteritems():
                if value == unpack_uint(self._replay[50:52]):
                    logger.debug('read_tag {0}={1} >>>'.format(tag, UNPACK_DATA_FUNCTION[key](self._replay[52:])))
                    return UNPACK_DATA_FUNCTION[key](self._replay[52:]), key
            logger.warning('read_tag returned none because data type is unknown>>>')
            return None
        else:
            logger.warning('read_tag returned None >>>')
            return None

    def write_tag(self, tag, value, typ):
        """ write_tag

        """
        logger.debug('>>> write_tag')
        if self.session == 0:
            logger.warning("Session not registered yet.")
            return None

        if not self.target_is_connected:
            if not self.forward_open():
                logger.warning("Target did not connected")
                return None

        rp = Cip.create_tag_rp(tag)

        if rp is None:
            logger.warning('Cannot create tag {0} request packet. Read not executed'.format(tag))
            return None

        # Creating the Message Request Packet
        message_request = [
            pack_uint(self._get_sequence()),
            chr(TAG_SERVICES_REQUEST["Write Tag"]),   # the Request Service
            chr(len(rp) / 2),               # the Request Path Size length in word
            rp,                             # the request path
            pack_uint(DATA_TYPE[typ]),    # data type
            pack_uint(1),                    # Add the number of tag to write
            PACK_DATA_FUNCTION[typ](value)
        ]
        logger.debug('writing tag:{0} value:{1} type:{2}'.format(tag, value, typ))
        ret_val = self.send_unit_data(
            Cip.build_common_cpf(
                DATA_ITEM['Connected'],
                ''.join(message_request),
                ADDRESS_ITEM['Connection Based'],
                addr_data=self.target_cid,
                timeout=1
            )
        )
        logger.debug('write_tag >>>')
        return ret_val

    def _get_symbol_object_instances(self, instance=0, time_out=10):
        """ _get_symbol_object_instances

        """
        if self.session == 0:
            print("Session not registered yet.")
            return None

        # Creating the Message Request Packet
        mr = [
            # Request Service
            chr(TAG_SERVICES_REQUEST['Get Instance Attribute List']),
            # the Request Path Size length in word
            chr(3),
            # Request Path ( 20 6B 25 00 Instance )
            CLASS_ID["8-bit"],       # Class id = 20 from spec 0x20
            CLASS_CODE["Symbol Object"],  # Logical segment: Symbolic Object 0x6B
            INSTANCE_ID["16-bit"],   # Instance Segment: 16 Bit instance 0x25
            '\x00',                       # Add pad byte because total length of Request path must be word-aligned
            pack_uint(instance),          # The instance
            # Request Data
            pack_uint(2),   # Number of attributes to retrieve
            pack_uint(1),   # Attribute 1: Symbol name
            pack_uint(2)    # Attribute 2: Symbol type
        ]

        # join the the list
        packet = ''.join(mr)

        # preparing the head of the Command Specific data
        head = [
            pack_dint(UCMM['Interface Handle']),    # The Interface Handle: should be 0
            pack_uint(time_out),                    # Timeout
            pack_uint(UCMM['Item Count']),          # Item Count: should be 2
            pack_uint(UCMM['Address Type ID']),     # Address Type ID: should be 0
            pack_uint(UCMM['Address Length']),      # Address Length: should be 0
            pack_uint(UCMM['Data Type ID']),        # Data Type ID: should be 0x00b2 or 178
            pack_uint(len(packet))                  # Length of the MR request packet
        ]

        # Command Specific Data is composed by head and packet
        command_specific_data = ''.join(head) + packet

        # Now put together Encapsulation Header and Command Specific Data
        self._message = self.build_header(ENCAPSULATION_COMMAND['send_rr_data'],
                                          len(command_specific_data)) + command_specific_data

        # Send the UCMM Request
        self.send()

        # Get replay
        self.receive()

    def send(self):
        try:
            logger.debug(print_bytes_msg(self._message,  'SEND --------------'))
            self.__sock.send(self._message)
        except SocketError as e:
            logger.error('Error {0} during {1}'.format(e, 'send'), exc_info=True)
            return False

        return True

    def receive(self):
        try:
            self._replay = self.__sock.receive()
            logger.debug(print_bytes_msg(self._replay, 'RECEIVE -----------'))
        except SocketError as e:
            logger.error('Error {0} during {1}'.format(e, 'receive'), exc_info=True)
            self._replay = None
            return False

        return True

    def open(self, ip_address, backplane=1, cpu_slot=0, rpi=5000):
        logger.debug('>>> open %s' % ip_address)
        # handle the socket layer
        self.backplane = backplane
        self.cpu_slot = cpu_slot
        self.rpi = rpi
        if not self.connection_opened:
            try:
                self.__sock.connect(ip_address, self.port)
                self.connection_opened = True
                if self.register_session() is None:
                    logger.warning("Session not registered")
                    logger.debug('open >>>')
                    return False
                logger.debug('open >>>')
                return True
            except SocketError as e:
                logger.error('Error {0} during {1}'.format(e, 'open'), exc_info=True)
        return False

    def close(self):
        logger.debug('>>> close')
        if self.target_is_connected:
            self.forward_close()
        if self.session != 0:
            self.un_register_session()
        self.__sock.close()
        self.__sock = None
        self.session = 0
        self.connection_opened = False
        logger.debug('close >>>')