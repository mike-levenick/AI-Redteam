FROM python:3.9-slim

# Install SSH and other dependencies
RUN apt-get update && apt-get install -y \
    openssh-server \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Create SSH directories (if they don't exist)
RUN mkdir -p /var/run/sshd

# Remove default MOTD and legal notices
RUN echo "" > /etc/motd && \
    rm -f /etc/update-motd.d/* && \
    chmod -x /etc/update-motd.d/* 2>/dev/null || true

# Disable last login message
RUN echo "PrintLastLog no" >> /etc/ssh/sshd_config

# Allow password authentication
# RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    # sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config
    
# Allow key-based authentication
RUN sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/PubkeyAuthentication no/PubkeyAuthentication yes/' /etc/ssh/sshd_config

# Set up Python environment
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy our LLM shell and related files
COPY llm_shell.py .
COPY system_prompt.py .
COPY knowledge_base.py .
COPY start.sh .
COPY knowledge/ /app/knowledge/
RUN chmod +x start.sh llm_shell.py

# Create a wrapper shell script for the LLM
RUN echo '#!/bin/bash' > /app/wrapper.sh && \
    echo '# Source environment variables' >> /app/wrapper.sh && \
    echo 'if [ -f /etc/profile.d/llm_env.sh ]; then' >> /app/wrapper.sh && \
    echo '    . /etc/profile.d/llm_env.sh' >> /app/wrapper.sh && \
    echo 'fi' >> /app/wrapper.sh && \
    echo 'cd /app' >> /app/wrapper.sh && \
    echo 'python3 /app/llm_shell.py' >> /app/wrapper.sh && \
    chmod +x /app/wrapper.sh && \
    echo '/app/wrapper.sh' >> /etc/shells

# Create users - add more users here by duplicating the useradd/chsh lines
# User 1: soryn
RUN for user in chris joe mike matt summer kevin john ty chase kelsey nick; do \
        useradd -m -s /app/wrapper.sh "$user" && \
        mkdir -p "/home/$user/.ssh" && \
        echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC02TEZK8mhKdqARLo2+y0dGbdl2EAdwvymB/WGQzujVv7q+AIkCP/oIXiv2ga64banSZSKKHl5xvpt9QQEJ5wwH4aQ7Jvus1VM4/AJRDan+1wYPHS1f45mJlUKi2PEoX9NJoPqIc6nBXAJESpzw9BgOzkfZOH3Czga0p8rR5pdZY3VllEmhj/yHH344LtL6neVbnOTzzvg50oqCoDZ3COMqbmWITT9XbxPmqGoajNcSiaBlwoCbJ0uxNsIXRXbnyOKdl5i2VFLUST70uM7ARm/BHt0t9QS8ShInj45w/Rle9LE7zzq5XpY/X5vAU1Ha0Iglj2KCmHDpEzN/7B3+VEbVZKD/Ofb5/1PDoBhOvLNcVeQQ/sa7oRNAhnkiFk13P+/mV0wHpRiJ8RrStqrohTDJbIegaZ7i3S7wn2ez04W3Xs9nBNJKxPcyhVz6zIKN9XW8eDUFEeTrmnBHEae1Jx11Gentb6Tywv/BjsE+UddXJe61ybXacOh2nSv9jRhMJ2I7buKbKYZkKbmLwMtT/Ads+Z6lFYTOSnsa1eoRrc82jLGDM6cT+04Ihgap8nJLSrCTG6i33/L6a28LkWsTVYcP15tQEeD7QcSZmcGbB7FzB9+R3qGzaVdQo0l5ZbSpMWxDdmwtBjTy/MJjxLeujdLSGtU9EO6Y6TtHhqtG9Sc8w==" > "/home/$user/.ssh/authorized_keys" && \
        chmod 700 "/home/$user/.ssh" && \
        chmod 600 "/home/$user/.ssh/authorized_keys" && \
        chown -R "$user:$user" "/home/$user/.ssh"; \
    done

EXPOSE 22

CMD ["/app/start.sh"]