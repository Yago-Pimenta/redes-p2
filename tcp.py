import asyncio
from tcputils import *
from collections import OrderedDict
import time


def split_into_segments(dados, tamanho_max):
    segments = []
    for i in range(0, len(dados), tamanho_max):
        segmento = dados[i:i+tamanho_max]
        segments.append(segmento)
    return segments



class Servidor:
    def __init__(self, rede, porta):
        self.rede =     rede
        self.porta =    porta
        self.conexoes =     {}
        self.callback =     None
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
        self.servidor =     servidor
        self.id_conexao =   id_conexao
        self.callback =     None
        self.seq_no =   seq_no
        self.next_seq_no =  seq_no + 1
        self.ack_no =   seq_no + 1
        self.timer_ativo =  False
        self.unconfirmed_data =     b""
        self.timer_active =     False
        self.timer = asyncio.get_event_loop().call_later(1, self._exemplo_timer)
        self.ack_list =     OrderedDict()  
        self.unacked_segments =     []



    def _exemplo_timer(self):
        # Esta função é só um exemplo e pode ser removida
        print('Este é um exemplo de como fazer um timer')

    def _rdt_rcv(self, received_seq_no, received_ack_no, received_flags, received_payload):
        src_addr,    src_port,  dst_addr,   dst_port =  self.id_conexao

        if received_seq_no != self.ack_no:
            return

        self.ack_no += len(received_payload)

        if (received_flags & FLAGS_FIN) == FLAGS_FIN:
            self.ack_no +=  1
            
            cabecalho = fix_checksum(make_header(dst_port, src_port, received_ack_no, self.ack_no, FLAGS_ACK), dst_addr, src_addr)

            self.servidor.rede.enviar(cabecalho, src_addr)

            print(self.servidor.conexoes)

            del self.servidor.conexoes[self.id_conexao]
            self.callback(self, b"")

        if (len(received_payload) == 0) and ((received_flags & FLAGS_ACK) == FLAGS_ACK):
            self.timer.cancel()
            self.timer_active =  False
            self.unconfirmed_data =   self.unconfirmed_data[received_ack_no - self.seq_no :]
            self.seq_no =   received_ack_no

            if received_ack_no < self.next_seq_no:
                self.timer_active= True
                self.timer = asyncio.get_event_loop().call_later(1, self._handle_timer)

            return

        self.seq_no =   received_ack_no
        
        cabecalho = fix_checksum(make_header(dst_port, src_port, self.seq_no, self.ack_no, FLAGS_ACK), dst_addr, src_addr)
        self.servidor.rede.enviar(cabecalho, src_addr)

        self.callback(self, received_payload)
        if received_ack_no > self.seq_no:
            sample_rtt = time.time() - self.ack_list.get(received_ack_no, 0)
            self.ack_list[received_ack_no] = time.time()

            if not self.EstimatedRTT:
                self.EstimatedRTT = sample_rtt
                self.DevRTT = sample_rtt / 2
            else:
                self.EstimatedRTT = (1 - 0.125) * self.EstimatedRTT + 0.125 * sample_rtt
                self.DevRTT = (1 - 0.25) * self.DevRTT + 0.25 * abs(sample_rtt - self.EstimatedRTT)

            # Calcula o TimeoutInterval
            self.TimeoutInterval = self.EstimatedRTT + 4 * self.DevRTT

        
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
        # TODO: implemente aqui o envio de dados.
        # Chame self.servidor.rede.enviar(segmento, dest_addr) para enviar o segmento
        # que você construir para a camada de rede.
        src_addr,   src_port,   dst_addr,   dst_port =  self.id_conexao
        
        for i in range(-(-len(dados) // MSS)):
            
            payload =   dados[i * MSS: (i + 1) * MSS]
            cabecalho = make_header(dst_port, src_port, self.next_seq_no, self.ack_no, FLAGS_ACK)
            segment = fix_checksum(cabecalho + payload, dst_addr, src_addr)

            self.unconfirmed_data +=     payload
            self.servidor.rede.enviar(segment, src_addr)
            self.next_seq_no +=     len(payload)

            # If timer not running, start timer
            if self.timer_active:
                print("Timer não foi iniciado")
            else:
                self.timer_active = True
                self.timer = asyncio.get_event_loop().call_later(1, self._handle_timer)
        if not self.timer_active:
             self.timer_active = True
             self.timer = asyncio.get_event_loop().call_later(self.TimeoutInterval, self._handle_timer)
        self._enviar_segmento_com_timer(segment)


    def _enviar_segmento(self, segmento):
        if not self.servidor.rede.fila:  # Verifica se a fila está vazia
            self.servidor.rede.fila.append((segmento, self.id_conexao[0]))




    def _tratar_segmentos_recebidos(self):
        while self.unacked_segments and self.unacked_segments[0] in self.ack_list:
            acked_segment = self.unacked_segments.pop(0)
            del self.ack_list[acked_segment]
        self.timer_active = False

    def _enviar_segmento_com_timer(self, segmento):
        self.unacked_segments.append(segmento)
        self.ack_list[segmento] = self.seq_no
        if not self.timer_ativo:
            self.timer_active= True
            self.timer = asyncio.get_event_loop().call_later(1, self._tratar_segmentos_recebidos)

    
    def _handle_timer(self):
        src_addr,   src_port,   dst_addr,   dst_port =  self.id_conexao
        cabecalho = fix_checksum(make_header(dst_port, src_port, self.seq_no, self.ack_no, FLAGS_ACK),dst_addr,src_addr)
        payload =   self.unconfirmed_data[:MSS]

        self.servidor.rede.enviar(cabecalho + payload, src_addr)

        self.timer = asyncio.get_event_loop().call_later(1, self._handle_timer)

        unconfirmed_segments = [segment for segment in self.unacked_segments if segment not in self.ack_list]

        # Reenvia os segmentos não confirmados
        for segment in unconfirmed_segments:
            self.servidor.rede.enviar(segment, self.id_conexao[0])

        # Reinicia o timer se houver segmentos não confirmados
        if unconfirmed_segments:
            self.timer_active = True
            self.timer = asyncio.get_event_loop().call_later(self.TimeoutInterval, self._handle_timer)
        else:
            self.timer_active = False


    def fechar(self):
        """
        Usado pela camada de aplicação para fechar a conexão
        """
        src_addr,   src_port,   dst_addr,   dst_port =  self.id_conexao
        cabecalho =  fix_checksum(make_header(dst_port, src_port, self.seq_no, self.ack_no, FLAGS_FIN),dst_addr,src_addr)
        self.servidor.rede.enviar(cabecalho, src_addr)
        if self.id_conexao in self.servidor.conexoes:
            del self.servidor.conexoes[self.id_conexao]
        
