import streamlit as st
from openai import OpenAI
from openai import AssistantEventHandler
from typing_extensions import override
import os
import re
import pandas as pd
import PyPDF2
import io
import json
try:
  from tokens import openai_key
except ImportError:
  openai_key = os.getenv('OPENAI_API_KEY')

class EventHandler(AssistantEventHandler):
    @override    
    def on_text_created(self, text) -> None:
        print(f"\nassistant > ", end="", flush=True)
    @override     
    def on_text_delta(self, delta, snapshot):
        print(delta.value, end="", flush=True)
        
def on_tool_call_created(self, tool_call):
  print(f"\nassistant > {tool_call.type}\n", flush=True)

def on_tool_call_delta(self, delta, snapshot):
  if delta.type == 'code_interpreter':
    if delta.code_interpreter.input:
      print(delta.code_interpreter.input, end="", flush=True)
    if delta.code_interpreter.outputs:
      print(f"\n\noutput >", flush=True)
      for output in delta.code_interpreter.outputs:
        if output.type == "logs":
          print(f"\n{output.logs}", flush=True)

def extract_text_from_pdf(pdf_file):
    reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

def process_invoice_with_ai(client, pdf_text):
    thread = client.beta.threads.create()
    message = client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=f"""Extraé la siguiente información de esta factura en formato JSON: 
        {{'Fecha': '...', 'Número de Factura': '...', 'CUIT Emisor': '...', 
        'Cliente': '...', 'Importe Total': '...', 'IVA': '...', 
        'Detalle de Productos': [
            {{'Descripción': '...', 'Cantidad': '...', 'Precio Unitario': '...', 'Subtotal': '...'}}
        ]}}
        
        Es muy importante que 'Detalle de Productos' sea un array de objetos con la información de cada producto.
        
        El texto de la factura es: 
        {pdf_text}"""
    )
    
    with client.beta.threads.runs.stream(
        thread_id=thread.id,
        assistant_id='asst_nnDTLYK0nrjuIBJCdscnA6vb',
        event_handler=EventHandler()) as stream:
            stream.until_done()
            bot_response = stream.get_final_messages()
            bot_reply = bot_response[0].content[0].text.value
            bot_reply = re.sub(r"【.*?】", "", bot_reply)
    
    return bot_reply

# Configuración inicial
col_title, col_logo = st.columns([5, 1])
with col_title:
  st.title("DASSA Bot - Procesador de Facturas")
with col_logo:
  st.image('logo.png')

client = OpenAI(
    api_key=openai_key)

# Inicializar variables de sesión
if 'processed_invoices' not in st.session_state:
    st.session_state.processed_invoices = []
    
if 'processed_products' not in st.session_state:
    st.session_state.processed_products = []

if 'conversation_started' not in st.session_state:
    st.session_state.conversation_started = True  # Set to True by default to show upload option immediately
    
if 'asking_for_more' not in st.session_state:
    st.session_state.asking_for_more = False
    
if 'finished' not in st.session_state:
    st.session_state.finished = False

# Mostrar mensajes de chat anteriores
if 'messages' not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "¡Hola! Soy DASSA-Bot. Sube una factura en PDF para procesarla. 🤖", "avatar": "avatar.png"}
    ]

for message in st.session_state.messages:
    st.chat_message(message["role"], avatar=message.get("avatar")).write(message["content"])

# Entrada del usuario
user_input = st.chat_input("Ingresa tu mensaje...")

# Subida de archivos - Mostrar siempre la opción de subir archivo si no estamos en estado de asking_for_more o finished
if not st.session_state.asking_for_more and not st.session_state.finished:
    pdf_file = st.file_uploader("Sube una factura en PDF", type=["pdf"], key=f"pdf_uploader_{len(st.session_state.processed_invoices)}")
    
    if pdf_file is not None:
        with st.spinner("Procesando factura..."):
            # Extraer texto del PDF
            pdf_text = extract_text_from_pdf(pdf_file)
            
            # Procesar la factura con OpenAI
            invoice_data_json = process_invoice_with_ai(client, pdf_text)
            
            # Parsear los datos JSON
            try:
                # Intentar extraer el JSON de la respuesta del bot
                json_match = re.search(r'\{.*\}', invoice_data_json, re.DOTALL)
                if json_match:
                    invoice_dict = json.loads(json_match.group())
                    
                    # Extraer productos y agregar información del encabezado a cada producto
                    products = []
                    if 'Detalle de Productos' in invoice_dict and isinstance(invoice_dict['Detalle de Productos'], list):
                        for product in invoice_dict['Detalle de Productos']:
                            # Añadir información del encabezado a cada producto
                            product_with_header = {
                                'Fecha': invoice_dict.get('Fecha', ''),
                                'Número de Factura': invoice_dict.get('Número de Factura', ''),
                                'CUIT Emisor': invoice_dict.get('CUIT Emisor', ''),
                                'Cliente': invoice_dict.get('Cliente', ''),
                                'Importe Total Factura': invoice_dict.get('Importe Total', ''),
                                'IVA': invoice_dict.get('IVA', ''),
                            }
                            # Añadir detalles del producto
                            product_with_header.update(product)
                            products.append(product_with_header)
                    
                    # Si no hay productos específicos, crear una fila con la información general
                    if not products:
                        products = [{
                            'Fecha': invoice_dict.get('Fecha', ''),
                            'Número de Factura': invoice_dict.get('Número de Factura', ''),
                            'CUIT Emisor': invoice_dict.get('CUIT Emisor', ''),
                            'Cliente': invoice_dict.get('Cliente', ''),
                            'Importe Total Factura': invoice_dict.get('Importe Total', ''),
                            'IVA': invoice_dict.get('IVA', ''),
                            'Descripción': 'Información general',
                            'Subtotal': invoice_dict.get('Importe Total', '')
                        }]
                    
                    # Guardar productos en session state
                    st.session_state.processed_products.extend(products)
                    
                    # Guardar factura completa
                    st.session_state.processed_invoices.append(invoice_dict)
                    
                    # Crear DataFrame para mostrar en pantalla
                    df_products = pd.DataFrame(products)
                    
                    # Mostrar tabla de productos
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": f"He analizado la factura. Aquí está la información de los productos:", 
                        "avatar": "avatar.png"
                    })
                    st.chat_message("assistant", avatar="avatar.png").write("He analizado la factura. Aquí está la información de los productos:")
                    
                    # Mostrar el DataFrame
                    st.dataframe(df_products)
                    
                    # Crear botones para continuar o finalizar
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.button("Agregar otra factura"):
                            st.session_state.messages.append({
                                "role": "assistant", 
                                "content": "Puedes subir otra factura.", 
                                "avatar": "avatar.png"
                            })
                            st.experimental_rerun()
                    
                    with col2:
                        if st.button("Finalizar y exportar"):
                            st.session_state.finished = True
                            st.experimental_rerun()
                else:
                    # Si no se puede extraer JSON válido
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": f"He analizado la factura pero no pude estructurar la información correctamente.\n\n{invoice_data_json}", 
                        "avatar": "avatar.png"
                    })
                    st.chat_message("assistant", avatar="avatar.png").write(f"He analizado la factura pero no pude estructurar la información correctamente.\n\n{invoice_data_json}")
                    st.session_state.processed_invoices.append({"Datos": invoice_data_json})
                    
                    # Crear botones para continuar o finalizar
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.button("Agregar otra factura"):
                            st.session_state.messages.append({
                                "role": "assistant", 
                                "content": "Puedes subir otra factura.", 
                                "avatar": "avatar.png"
                            })
                            st.experimental_rerun()
                    
                    with col2:
                        if st.button("Finalizar y exportar"):
                            st.session_state.finished = True
                            st.experimental_rerun()
            except Exception as e:
                st.warning(f"No se pudo extraer JSON estructurado: {e}")
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": f"Ocurrió un error al procesar la factura: {str(e)}", 
                    "avatar": "avatar.png"
                })
                st.chat_message("assistant", avatar="avatar.png").write(f"Ocurrió un error al procesar la factura: {str(e)}")
                st.session_state.processed_invoices.append({"Datos": invoice_data_json})
                
                # Crear botones para continuar o finalizar
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("Agregar otra factura"):
                        st.session_state.messages.append({
                            "role": "assistant", 
                            "content": "Puedes subir otra factura.", 
                            "avatar": "avatar.png"
                        })
                        st.experimental_rerun()
                
                with col2:
                    if st.button("Finalizar y exportar"):
                        st.session_state.finished = True
                        st.experimental_rerun()

# Procesar la entrada del usuario
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.chat_message("user").write(user_input)
    
    try:
        thread = client.beta.threads.create()
        message = client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_input
        )
        with client.beta.threads.runs.stream(
            thread_id=thread.id,
            assistant_id='asst_nnDTLYK0nrjuIBJCdscnA6vb',
            event_handler=EventHandler()) as stream:
                stream.until_done()
                bot_response = stream.get_final_messages()
                bot_reply = bot_response[0].content[0].text.value
                bot_reply = re.sub(r"【.*?】", "", bot_reply)
        
        st.session_state.messages.append({"role": "assistant", "content": bot_reply, "avatar": "avatar.png"})
        st.chat_message("assistant", avatar="avatar.png").write(bot_reply)
    except Exception as e:
        st.error(f"Error: {e}")

# Si ya terminamos de procesar, mostrar el Excel
if st.session_state.finished:    
    # Crear DataFrame y archivo Excel con datos a nivel de producto
    if st.session_state.processed_products:
        df = pd.DataFrame(st.session_state.processed_products)
        
        # Crear buffer de bytes para el archivo Excel
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Productos')
        excel_data = excel_buffer.getvalue()
        
        # Mostrar enlace de descarga
        st.session_state.messages.append({
            "role": "assistant", 
            "content": "Aquí está el archivo Excel con todos los productos de las facturas procesadas:", 
            "avatar": "avatar.png"
        })
        st.chat_message("assistant", avatar="avatar.png").write("Aquí está el archivo Excel con todos los productos de las facturas procesadas:")
        
        # Mostrar DataFrame en chat
        st.dataframe(df)
        
        # Enlace de descarga
        st.download_button(
            label="Descargar Excel de Productos",
            data=excel_data,
            file_name="productos_facturas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # Botón para reiniciar
        if st.button("Procesar nuevas facturas"):
            st.session_state.processed_invoices = []
            st.session_state.processed_products = []
            st.session_state.finished = False
            st.session_state.messages = [
                {"role": "assistant", "content": "¡Hola! Soy DASSA-Bot. Sube una factura en PDF para procesarla. 🤖", "avatar": "avatar.png"}
            ]
            st.experimental_rerun()
    else:
        st.warning("No se procesaron facturas.")
        # Botón para reiniciar
        if st.button("Procesar facturas"):
            st.session_state.processed_invoices = []
            st.session_state.processed_products = []
            st.session_state.finished = False
            st.session_state.messages = [
                {"role": "assistant", "content": "¡Hola! Soy DASSA-Bot. Sube una factura en PDF para procesarla. 🤖", "avatar": "avatar.png"}
            ]
            st.experimental_rerun()

