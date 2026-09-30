root /usr/share/nginx/html;
index index.html;
client_max_body_size 20m;

location = /gateway-health {
    access_log off;
    default_type text/plain;
    return 200 "ok\n";
}

location /django/api/ {
    proxy_pass http://django_api:8000/api/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto https;
}

location /spring/api/ {
    proxy_pass http://spring_api:8081/api/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto https;
}

location /media/ {
    proxy_pass http://storage:9000/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto https;
}

location / {
    try_files $uri $uri/ /index.html;
}
