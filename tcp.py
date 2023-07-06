import asyncio
from tcputils import *
from collections import OrderedDict



class Servidor:
    def __init__(self, rede, porta):
        self.rede = rede
        self.porta = porta
        self.conexoes = {}
        self.callback = None
        self.rede.registrar_recebedor(self._rdt_rcv)

    def registrar_monitor_de_conexoes_aceitas(self, callback):
        """
            Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que uma nova conexão for aceita
        """
        self.callback = callback
    #1
    def _rdt_rcv(self, src_addr, dst_addr, segment):
        src_port, dst_port, seq_no, ack_no, flags, window_size, checksum, urg_ptr = read_header(segment)

        if dst_port != self.porta:
            # Ignora segmentos que não são destinados à porta do nosso servidor
            print("ERRO! Porta não destinada")
            return
        if not self.rede.ignore_checksum and calc_checksum(segment, src_addr, dst_addr) != 0:
            print("descartando segmento com checksum incorreto")
            return

        payload = segment[4 * (flags >> 12):]
        id_conexao = src_addr, src_port, dst_addr, dst_port

        if (flags & FLAGS_SYN) == FLAGS_SYN:
            # A flag SYN estar setada significa que é um cliente tentando estabelecer uma conexão nova
            conexao = self.conexoes[id_conexao] = Conexao(self, id_conexao, seq_no)
            ack_no = seq_no + 1
            header = fix_checksum(make_header(dst_port, src_port, seq_no, ack_no, FLAGS_SYN + FLAGS_ACK), dst_addr, src_addr)

            self.rede.enviar(header, src_addr)

            if self.callback:
                self.callback(conexao)

            # Receive ACK segment from the client
            if (flags & FLAGS_ACK) == FLAGS_ACK:
                self.conexoes[id_conexao]._rdt_rcv(seq_no, ack_no, flags, payload)

        elif id_conexao in self.conexoes:
            self.conexoes[id_conexao]._rdt_rcv(seq_no, ack_no, flags, payload)

        else:
            print(f"{src_addr}:{src_port} -> {dst_addr}:{dst_port} (ERRO: pacote associado a conexão desconhecida)")
        



class Conexao:
    def __init__(self, servidor, id_conexao, seq_no):
        self.servidor = servidor
        self.id_conexao = id_conexao
        self.callback = None
        self.seq_no = seq_no
        self.nex_seq_no = seq_no + 1
        self.ack_no = seq_no + 1
        self.timer_ativo = False
        self.nao_confirmado = b""
        self.timer = asyncio.get_event_loop().call_later(1, self._exemplo_timer)
        self.ack_list = OrderedDict()  # Create an ordered dictionary for acknowledgment numbers
        self.unacked_segments = []
        self.timer_ativo = False

    # Rest of the class implementation...


    def _exemplo_timer(self):
        # Esta função é só um exemplo e pode ser removida
        print('Este é um exemplo de como fazer um timer')

    def _rdt_rcv(self, seq_no, ack_no, flags, payload):
        """
        Handles the reception of segments from the network layer
        """
        #2
        if seq_no == self.nex_seq_no and (flags & FLAGS_ACK) == FLAGS_ACK:
            # Segment received in order
            self.nex_seq_no += len(payload)
            self.ack_no = seq_no + len(payload)
            self.callback(self, payload)  # Pass the received data to the application layer
        elif seq_no < self.nex_seq_no:
            # Duplicate segment received, retransmit acknowledgment
            ack_no = self.nex_seq_no
            header = fix_checksum(make_header(
                self.id_conexao[3], self.id_conexao[1], self.seq_no, ack_no, FLAGS_ACK),
                self.id_conexao[2], self.id_conexao[0])
            self.servidor.rede.enviar(header, self.id_conexao[0])
        else:
            # Out-of-order segment received, ignore it for now
            pass

        if (flags & FLAGS_ACK) == FLAGS_ACK:
            ack_segment = fix_checksum(make_header(
                self.id_conexao[3], self.id_conexao[1], self.seq_no, self.ack_no, FLAGS_ACK),
                self.id_conexao[2], self.id_conexao[0])
            self.servidor.rede.enviar(ack_segment, self.id_conexao[0])

    # Os métodos abaixo fazem parte da API

    def registrar_recebedor(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que dados forem corretamente recebidos
        """
        self.callback = callback

    def enviar(self, dados):
        """
        Usado pela camada de aplicação para enviar dados
        """
        #2
        segmento = fix_checksum(make_header(
            self.id_conexao[3], self.id_conexao[1], self.seq_no, self.ack_no, FLAGS_ACK) + dados,
            self.id_conexao[2], self.id_conexao[0])
        self.servidor.rede.enviar(segmento, self.id_conexao[0])
        #3
        payload_segments = split_into_segments(dados, MSS)  
        for segment in payload_segments:
            self.unacked_segments.append(segment)
            self._enviar_segmento(segment)


    def fechar(self):
        """
        Usado pela camada de aplicação para fechar a conexão
        """
        if self.id_conexao in self.servidor.conexoes:
            del self.servidor.conexoes[self.id_conexao]
